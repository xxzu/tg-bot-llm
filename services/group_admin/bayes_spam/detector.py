"""群消息广告检测入口。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from config import performance as perf
from services.group_admin.bayes_spam import rules
from services.group_admin.bayes_spam import store

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    is_spam: bool
    p_spam: float = 0.0
    source: str = ""  # rule | cache | bayes


class BayesSpamDetector:
    """参考 bayes_spam_sniper SpamDetectionService 的检测流程。"""

    def __init__(
        self,
        *,
        probability_threshold: float | None = None,
        chinese_space_threshold: float | None = None,
        short_message_word_threshold: int | None = None,
    ):
        self.probability_threshold = (
            probability_threshold
            if probability_threshold is not None
            else perf.BAYES_SPAM_THRESHOLD
        )
        self.chinese_space_threshold = (
            chinese_space_threshold
            if chinese_space_threshold is not None
            else perf.BAYES_CHINESE_SPACE_THRESHOLD
        )
        self.short_message_word_threshold = (
            short_message_word_threshold
            if short_message_word_threshold is not None
            else perf.BAYES_SHORT_MESSAGE_WORD_THRESHOLD
        )

    async def ensure_ready(self, chat_id: int) -> None:
        scope = store.scope_for_chat(chat_id)
        await store.seed_if_empty(
            store.SCOPE_GLOBAL,
            probability_threshold=self.probability_threshold,
            short_message_word_threshold=self.short_message_word_threshold,
        )
        await store.seed_if_empty(
            scope,
            probability_threshold=self.probability_threshold,
            short_message_word_threshold=self.short_message_word_threshold,
        )

    async def classify_message(
        self,
        text: str,
        *,
        chat_id: int,
        user_display_name: str = "",
    ) -> ClassificationResult:
        if not perf.BAYES_SPAM_ENABLED:
            return ClassificationResult(False)
        body = (text or "").strip()
        if not body:
            return ClassificationResult(False)

        await self.ensure_ready(chat_id)

        rule = rules.check_chinese_spacing_spam(
            body, ratio_threshold=self.chinese_space_threshold
        )
        if rule.is_spam:
            return ClassificationResult(True, 1.0, "rule")

        for target, value in (
            ("message_content", body),
            ("user_name", (user_display_name or "").strip()),
        ):
            if not value:
                continue
            hit = await self._classify_target(value, chat_id=chat_id, target=target)
            if hit.is_spam:
                return hit
        return ClassificationResult(False)

    async def _classify_target(
        self, text: str, *, chat_id: int, target: str
    ) -> ClassificationResult:
        scopes = [store.scope_for_chat(chat_id), store.SCOPE_GLOBAL]
        for scope in scopes:
            label = await store.get_sample_label(text, scope, target)
            if label == "spam":
                return ClassificationResult(True, 1.0, "cache")
            if label == "ham":
                return ClassificationResult(False, 0.0, "cache")

        # 优先用本群模型，再回退全局
        for scope in scopes:
            clf = await store.load_classifier(
                scope,
                probability_threshold=self.probability_threshold,
                short_message_word_threshold=self.short_message_word_threshold,
            )
            is_spam, p_spam = clf.classify(text)
            if is_spam:
                logger.info(
                    "bayes spam scope=%s target=%s p=%.4f text=%r",
                    scope,
                    target,
                    p_spam,
                    text[:80],
                )
                return ClassificationResult(True, p_spam, "bayes")
        return ClassificationResult(False)

    async def train_spam(
        self,
        text: str,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        training_target: str = "message_content",
    ) -> None:
        scope = store.scope_for_chat(chat_id)
        await store.upsert_sample(
            text=text,
            scope=scope,
            label="spam",
            training_target=training_target,
            chat_id=chat_id,
            user_id=user_id,
        )
        await store.upsert_sample(
            text=text,
            scope=store.SCOPE_GLOBAL,
            label="spam",
            training_target=training_target,
            chat_id=chat_id,
            user_id=user_id,
        )
        await store.train_and_save(
            scope,
            text,
            is_spam=True,
            probability_threshold=self.probability_threshold,
            short_message_word_threshold=self.short_message_word_threshold,
        )

    async def train_ham(
        self,
        text: str,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        training_target: str = "message_content",
    ) -> None:
        scope = store.scope_for_chat(chat_id)
        await store.upsert_sample(
            text=text,
            scope=scope,
            label="ham",
            training_target=training_target,
            chat_id=chat_id,
            user_id=user_id,
        )
        await store.upsert_sample(
            text=text,
            scope=store.SCOPE_GLOBAL,
            label="ham",
            training_target=training_target,
            chat_id=chat_id,
            user_id=user_id,
        )
        await store.train_and_save(
            scope,
            text,
            is_spam=False,
            probability_threshold=self.probability_threshold,
            short_message_word_threshold=self.short_message_word_threshold,
        )


_detector: Optional[BayesSpamDetector] = None


def get_detector() -> BayesSpamDetector:
    global _detector
    if _detector is None:
        _detector = BayesSpamDetector()
    return _detector
