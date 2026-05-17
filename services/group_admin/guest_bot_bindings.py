"""群内访客/广告机器人与真人用户的持久绑定（同群同 bot 后续消息归责）。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import aiosqlite

from services.group_admin.repo import DB_FILE

logger = logging.getLogger(__name__)

# (chat_id, bot_user_id) -> (caller_user_id, caller_username)
BindingEntry = Tuple[int, str]


class GuestBotBindingStore:
    def __init__(self) -> None:
        self._cache: Dict[Tuple[int, int], BindingEntry] = {}

    async def ensure_table(self, conn: aiosqlite.Connection) -> None:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guest_bot_bindings (
                chat_id INTEGER NOT NULL,
                bot_user_id INTEGER NOT NULL,
                caller_user_id INTEGER NOT NULL,
                caller_username TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, bot_user_id)
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_guest_bot_bindings_caller "
            "ON guest_bot_bindings(chat_id, caller_user_id)"
        )

    async def load_all(self) -> None:
        self._cache.clear()
        async with aiosqlite.connect(DB_FILE) as conn:
            await self.ensure_table(conn)
            async with conn.execute(
                "SELECT chat_id, bot_user_id, caller_user_id, caller_username "
                "FROM guest_bot_bindings"
            ) as cur:
                rows = await cur.fetchall()
        for chat_id, bot_id, caller_id, caller_name in rows:
            self._cache[(int(chat_id), int(bot_id))] = (
                int(caller_id),
                caller_name or str(caller_id),
            )
        logger.info("已加载访客机器人绑定 %s 条", len(self._cache))

    async def bind(
        self,
        chat_id: int,
        bot_user_id: int,
        caller_user_id: int,
        caller_username: str = "",
    ) -> None:
        name = caller_username or str(caller_user_id)
        key = (int(chat_id), int(bot_user_id))
        prev = self._cache.get(key)
        self._cache[key] = (int(caller_user_id), name)
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await self.ensure_table(conn)
            await conn.execute(
                """
                INSERT INTO guest_bot_bindings (
                    chat_id, bot_user_id, caller_user_id, caller_username, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, bot_user_id) DO UPDATE SET
                    caller_user_id = excluded.caller_user_id,
                    caller_username = excluded.caller_username,
                    updated_at = excluded.updated_at
                """,
                (
                    chat_id,
                    bot_user_id,
                    caller_user_id,
                    name,
                    datetime.now(),
                ),
            )
            await conn.commit()
        if prev and prev[0] != caller_user_id:
            logger.info(
                "访客机器人绑定更新 chat_id=%s bot_id=%s %s→%s",
                chat_id,
                bot_user_id,
                prev[0],
                caller_user_id,
            )
        else:
            logger.info(
                "访客机器人绑定 chat_id=%s bot_id=%s → caller_id=%s username=%s",
                chat_id,
                bot_user_id,
                caller_user_id,
                name,
            )

    def lookup_sync(self, chat_id: int, bot_user_id: int) -> Optional[BindingEntry]:
        return self._cache.get((int(chat_id), int(bot_user_id)))

    async def lookup(self, chat_id: int, bot_user_id: int) -> Optional[BindingEntry]:
        hit = self.lookup_sync(chat_id, bot_user_id)
        if hit:
            return hit
        async with aiosqlite.connect(DB_FILE) as conn:
            await self.ensure_table(conn)
            async with conn.execute(
                """
                SELECT caller_user_id, caller_username
                FROM guest_bot_bindings
                WHERE chat_id = ? AND bot_user_id = ?
                """,
                (chat_id, bot_user_id),
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        entry = (int(row[0]), row[1] or str(row[0]))
        self._cache[(int(chat_id), int(bot_user_id))] = entry
        return entry

    def list_bots_for_caller(self, chat_id: int, caller_user_id: int) -> List[int]:
        """某真人在本群绑定过的机器人 ID 列表。"""
        cid = int(chat_id)
        uid = int(caller_user_id)
        return [
            bot_id
            for (c, bot_id), (caller_id, _) in self._cache.items()
            if c == cid and caller_id == uid
        ]

    async def list_bots_for_caller_async(
        self, chat_id: int, caller_user_id: int
    ) -> List[int]:
        found = self.list_bots_for_caller(chat_id, caller_user_id)
        if found:
            return found
        async with aiosqlite.connect(DB_FILE) as conn:
            await self.ensure_table(conn)
            async with conn.execute(
                """
                SELECT bot_user_id FROM guest_bot_bindings
                WHERE chat_id = ? AND caller_user_id = ?
                """,
                (chat_id, caller_user_id),
            ) as cur:
                rows = await cur.fetchall()
        return [int(r[0]) for r in rows]
