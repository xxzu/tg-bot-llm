"""群管内容策略（关键词判定）。"""
from __future__ import annotations

from typing import Dict, Optional, Set

from services.group_admin.keywords import default_keyword_set, match_violation


class GroupKeywordPolicy:
    def __init__(self) -> None:
        self.default_banned_keywords = default_keyword_set()
        self.chat_banned_keywords: Dict[int, Set[str]] = {}

    def effective_keywords(self, chat_id: int) -> Set[str]:
        custom = self.chat_banned_keywords.get(chat_id, set())
        return self.default_banned_keywords | custom

    def check(self, chat_id: int, text: str) -> Optional[str]:
        return match_violation(text, self.effective_keywords(chat_id))
