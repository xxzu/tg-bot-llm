"""LLM 会话契约（不绑定 Telegram / UserData 实现）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


@dataclass
class ConversationSnapshot:
    messages: List[dict]
    voice_answer: bool = False
    voice_type: str = "cat"

    @classmethod
    def from_user_data(cls, user_data: Any) -> "ConversationSnapshot":
        return cls(
            messages=list(user_data.messages),
            voice_answer=bool(getattr(user_data, "voice_answer", False)),
            voice_type=getattr(user_data, "voice_type", "cat") or "cat",
        )

    @classmethod
    def from_session(cls, session: Any) -> "ConversationSnapshot":
        return cls(
            messages=list(session.messages),
            voice_answer=session.voice_answer,
            voice_type=session.voice_type,
        )
