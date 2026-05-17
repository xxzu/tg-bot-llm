"""贝叶斯模型 SQLite 持久化（独立库 data/bayes_spam.db）。"""
from __future__ import annotations

import hashlib
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import aiosqlite

from services.group_admin.bayes_spam.classifier import ClassifierState, NaiveBayesSpamClassifier
from services.group_admin.bayes_spam.repo import BAYES_DB_FILE
from services.group_admin.repo import DB_FILE as GROUP_ADMIN_DB_FILE

logger = logging.getLogger(__name__)
_legacy_migrated = False

SCOPE_GLOBAL = "global"
SCOPE_CHAT_PREFIX = "chat:"


def scope_for_chat(chat_id: int | None) -> str:
    if chat_id is None or chat_id == 0:
        return SCOPE_GLOBAL
    return f"{SCOPE_CHAT_PREFIX}{chat_id}"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@asynccontextmanager
async def bayes_db() -> AsyncIterator[aiosqlite.Connection]:
    BAYES_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(BAYES_DB_FILE) as conn:
        await ensure_tables(conn)
        global _legacy_migrated
        if not _legacy_migrated:
            await _migrate_legacy_from_group_admin(conn)
            _legacy_migrated = True
        yield conn


async def _migrate_legacy_from_group_admin(conn: aiosqlite.Connection) -> None:
    """若旧版写在 group_admin.db 的 bayes_* 表有数据，一次性迁入 bayes_spam.db。"""
    if not GROUP_ADMIN_DB_FILE.exists():
        return
    async with conn.execute(
        "SELECT COUNT(*) FROM bayes_classifier_state"
    ) as cur:
        if (await cur.fetchone())[0] > 0:
            return
    try:
        async with aiosqlite.connect(GROUP_ADMIN_DB_FILE) as old:
            async with old.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bayes_classifier_state'"
            ) as cur:
                if not await cur.fetchone():
                    return
            async with old.execute(
                "SELECT scope, spam_counts, ham_counts, total_spam_words, total_ham_words,"
                " total_spam_messages, total_ham_messages, vocabulary_size"
                " FROM bayes_classifier_state"
            ) as cur:
                rows = await cur.fetchall()
            for row in rows:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO bayes_classifier_state (
                        scope, spam_counts, ham_counts,
                        total_spam_words, total_ham_words,
                        total_spam_messages, total_ham_messages, vocabulary_size
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
            async with old.execute(
                "SELECT content_hash, scope, training_target, message_text, label, chat_id, user_id"
                " FROM bayes_trained_samples"
            ) as cur:
                samples = await cur.fetchall()
            for row in samples:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO bayes_trained_samples (
                        content_hash, scope, training_target, message_text, label, chat_id, user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
            await conn.commit()
            if rows or samples:
                logger.info(
                    "已从 group_admin.db 迁移贝叶斯数据: states=%s samples=%s",
                    len(rows),
                    len(samples),
                )
    except Exception as e:
        logger.warning("迁移旧 bayes 表失败（可忽略）: %s", e)


async def ensure_tables(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bayes_classifier_state (
            scope TEXT PRIMARY KEY,
            spam_counts TEXT NOT NULL DEFAULT '{}',
            ham_counts TEXT NOT NULL DEFAULT '{}',
            total_spam_words INTEGER NOT NULL DEFAULT 0,
            total_ham_words INTEGER NOT NULL DEFAULT 0,
            total_spam_messages INTEGER NOT NULL DEFAULT 0,
            total_ham_messages INTEGER NOT NULL DEFAULT 0,
            vocabulary_size INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bayes_trained_samples (
            content_hash TEXT NOT NULL,
            scope TEXT NOT NULL,
            training_target TEXT NOT NULL DEFAULT 'message_content',
            message_text TEXT NOT NULL,
            label TEXT NOT NULL,
            chat_id INTEGER,
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (content_hash, scope, training_target)
        )
        """
    )
    await conn.commit()


def _state_from_row(row: tuple) -> ClassifierState:
    (
        _scope,
        spam_json,
        ham_json,
        tsw,
        thw,
        tsm,
        thm,
        vocab,
    ) = row
    return ClassifierState(
        spam_counts=json.loads(spam_json or "{}"),
        ham_counts=json.loads(ham_json or "{}"),
        total_spam_words=int(tsw or 0),
        total_ham_words=int(thw or 0),
        total_spam_messages=int(tsm or 0),
        total_ham_messages=int(thm or 0),
        vocabulary_size=int(vocab or 0),
    )


async def load_state(scope: str) -> ClassifierState:
    async with bayes_db() as conn:
        async with conn.execute(
            "SELECT scope, spam_counts, ham_counts, total_spam_words, total_ham_words,"
            " total_spam_messages, total_ham_messages, vocabulary_size"
            " FROM bayes_classifier_state WHERE scope = ?",
            (scope,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return ClassifierState()
        return _state_from_row(row)


async def save_state(scope: str, state: ClassifierState) -> None:
    async with bayes_db() as conn:
        await conn.execute(
            """
            INSERT INTO bayes_classifier_state (
                scope, spam_counts, ham_counts,
                total_spam_words, total_ham_words,
                total_spam_messages, total_ham_messages, vocabulary_size, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(scope) DO UPDATE SET
                spam_counts=excluded.spam_counts,
                ham_counts=excluded.ham_counts,
                total_spam_words=excluded.total_spam_words,
                total_ham_words=excluded.total_ham_words,
                total_spam_messages=excluded.total_spam_messages,
                total_ham_messages=excluded.total_ham_messages,
                vocabulary_size=excluded.vocabulary_size,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                scope,
                json.dumps(state.spam_counts, ensure_ascii=False),
                json.dumps(state.ham_counts, ensure_ascii=False),
                state.total_spam_words,
                state.total_ham_words,
                state.total_spam_messages,
                state.total_ham_messages,
                state.vocabulary_size,
            ),
        )
        await conn.commit()


async def get_sample_label(
    text: str, scope: str, training_target: str = "message_content"
) -> Optional[str]:
    h = content_hash(text)
    async with bayes_db() as conn:
        async with conn.execute(
            "SELECT label FROM bayes_trained_samples"
            " WHERE content_hash = ? AND scope = ? AND training_target = ?",
            (h, scope, training_target),
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else None


async def upsert_sample(
    *,
    text: str,
    scope: str,
    label: str,
    training_target: str = "message_content",
    chat_id: int | None = None,
    user_id: int | None = None,
) -> None:
    h = content_hash(text)
    async with bayes_db() as conn:
        await conn.execute(
            """
            INSERT INTO bayes_trained_samples (
                content_hash, scope, training_target, message_text, label, chat_id, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(content_hash, scope, training_target) DO UPDATE SET
                label=excluded.label,
                message_text=excluded.message_text,
                chat_id=excluded.chat_id,
                user_id=excluded.user_id,
                created_at=CURRENT_TIMESTAMP
            """,
            (h, scope, training_target, text, label, chat_id, user_id),
        )
        await conn.commit()


async def load_classifier(
    scope: str,
    *,
    probability_threshold: float,
    short_message_word_threshold: int,
) -> NaiveBayesSpamClassifier:
    state = await load_state(scope)
    return NaiveBayesSpamClassifier(
        state,
        probability_threshold=probability_threshold,
        short_message_word_threshold=short_message_word_threshold,
    )


async def train_and_save(
    scope: str,
    text: str,
    *,
    is_spam: bool,
    probability_threshold: float,
    short_message_word_threshold: int,
    also_global: bool = True,
) -> NaiveBayesSpamClassifier:
    clf = await load_classifier(
        scope,
        probability_threshold=probability_threshold,
        short_message_word_threshold=short_message_word_threshold,
    )
    clf.train(text, is_spam=is_spam)
    await save_state(scope, clf.state)
    if also_global and scope != SCOPE_GLOBAL:
        g = await load_classifier(
            SCOPE_GLOBAL,
            probability_threshold=probability_threshold,
            short_message_word_threshold=short_message_word_threshold,
        )
        g.train(text, is_spam=is_spam)
        await save_state(SCOPE_GLOBAL, g.state)
    return clf


DEFAULT_SPAM_SEEDS = [
    "加微信刷单日赚上千兼职",
    "扫码领取红包限时优惠投资理财",
    "一手出微信支付宝抖音淘宝需要联系",
    "CDN加速服务器免备案大带宽直播推拉流",
]
DEFAULT_HAM_SEEDS = [
    "好的谢谢",
    "哈哈哈笑死",
    "今天天气不错",
    "这个问题我也不确定",
]


async def seed_if_empty(
    scope: str,
    *,
    probability_threshold: float,
    short_message_word_threshold: int,
) -> None:
    state = await load_state(scope)
    if state.total_spam_messages > 0 and state.total_ham_messages > 0:
        return
    for s in DEFAULT_SPAM_SEEDS:
        await train_and_save(
            scope,
            s,
            is_spam=True,
            probability_threshold=probability_threshold,
            short_message_word_threshold=short_message_word_threshold,
            also_global=False,
        )
    for h in DEFAULT_HAM_SEEDS:
        await train_and_save(
            scope,
            h,
            is_spam=False,
            probability_threshold=probability_threshold,
            short_message_word_threshold=short_message_word_threshold,
            also_global=False,
        )
