"""广告拦截记录（对齐 bayes_spam_sniper 的 TrainedMessage / listspam）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from services.group_admin.bayes_spam.store import bayes_db

LABEL_MAYBE_SPAM = "maybe_spam"
LABEL_SPAM = "spam"
LABEL_HAM = "ham"

SOURCE_AUTO = "auto"
SOURCE_MARKSPAM = "markspam"
SOURCE_FEEDSPAM = "feedspam"
SOURCE_MARKHAM = "markham"


@dataclass
class SpamLogEntry:
    id: int
    chat_id: int
    message_id: Optional[int]
    user_id: Optional[int]
    username: str
    message_text: str
    p_spam: float
    label: str
    source: str
    created_at: str


async def _ensure_spam_log_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bayes_spam_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message_id INTEGER,
            user_id INTEGER,
            username TEXT,
            message_text TEXT NOT NULL,
            p_spam REAL,
            label TEXT NOT NULL DEFAULT 'maybe_spam',
            source TEXT NOT NULL DEFAULT 'auto',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_spam_log_chat ON bayes_spam_log(chat_id, created_at DESC)"
    )
    await conn.commit()


async def log_detection(
    *,
    chat_id: int,
    message_text: str,
    p_spam: float = 1.0,
    label: str = LABEL_MAYBE_SPAM,
    source: str = SOURCE_AUTO,
    message_id: Optional[int] = None,
    user_id: Optional[int] = None,
    username: str = "",
) -> int:
    async with bayes_db() as conn:
        await _ensure_spam_log_table(conn)
        cur = await conn.execute(
            """
            INSERT INTO bayes_spam_log (
                chat_id, message_id, user_id, username, message_text, p_spam, label, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                message_id,
                user_id,
                username,
                message_text[:2000],
                p_spam,
                label,
                source,
            ),
        )
        await conn.commit()
        return int(cur.lastrowid)


async def count_user_spam_in_chat(chat_id: int, user_id: int) -> int:
    """本群内因广告被记录的次数（maybe_spam + spam）。"""
    async with bayes_db() as conn:
        await _ensure_spam_log_table(conn)
        async with conn.execute(
            """
            SELECT COUNT(*) FROM bayes_spam_log
            WHERE chat_id = ? AND user_id = ? AND label IN ('maybe_spam', 'spam')
            """,
            (chat_id, user_id),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0] if row else 0)


async def list_recent(
    chat_id: int,
    *,
    limit: int = 10,
    labels: tuple = (LABEL_MAYBE_SPAM, LABEL_SPAM),
) -> List[SpamLogEntry]:
    limit = max(1, min(limit, 30))
    placeholders = ",".join("?" * len(labels))
    async with bayes_db() as conn:
        await _ensure_spam_log_table(conn)
        async with conn.execute(
            f"""
            SELECT id, chat_id, message_id, user_id, username, message_text,
                   p_spam, label, source, created_at
            FROM bayes_spam_log
            WHERE chat_id = ? AND label IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (chat_id, *labels, limit),
        ) as cur:
            rows = await cur.fetchall()
    return [
        SpamLogEntry(
            id=r[0],
            chat_id=r[1],
            message_id=r[2],
            user_id=r[3],
            username=r[4] or "",
            message_text=r[5],
            p_spam=float(r[6] or 0),
            label=r[7],
            source=r[8],
            created_at=str(r[9]),
        )
        for r in rows
    ]


async def mark_log_as_ham(log_id: int, chat_id: int) -> Optional[str]:
    async with bayes_db() as conn:
        await _ensure_spam_log_table(conn)
        async with conn.execute(
            "SELECT message_text FROM bayes_spam_log WHERE id = ? AND chat_id = ?",
            (log_id, chat_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        text = row[0]
        await conn.execute(
            "UPDATE bayes_spam_log SET label = ?, source = ? WHERE id = ? AND chat_id = ?",
            (LABEL_HAM, SOURCE_MARKHAM, log_id, chat_id),
        )
        await conn.commit()
        return text
