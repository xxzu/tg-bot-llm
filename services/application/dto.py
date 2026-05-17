"""应用层 DTO（不依赖 aiogram）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional


class ReplyDeliveryMode(str, Enum):
    NONE = "none"
    STREAM_ALREADY_SENT = "stream"
    PLACEHOLDER_THEN_EDIT = "placeholder"
    VOICE_ONLY = "voice"


@dataclass
class IncomingChatContext:
    user_id: int
    chat_id: int
    chat_type: str
    message_text: str
    has_voice: bool
    is_reply_to_bot: bool
    is_mention: bool
    has_wake_word: bool


@dataclass
class ChatSessionContext:
    """当前对话会话（读写仍由 UserData 持久化）。"""

    storage_user_id: int
    storage_chat_id: int
    model_id: str
    system_message: str
    messages: List[dict]
    voice_answer: bool
    voice_type: str
    count_messages: int = 0

    @classmethod
    def from_user_data(cls, user_data: Any, *, storage_user_id: int, storage_chat_id: int) -> "ChatSessionContext":
        return cls(
            storage_user_id=storage_user_id,
            storage_chat_id=storage_chat_id,
            model_id=user_data.model,
            system_message=user_data.system_message or "",
            messages=user_data.messages,
            voice_answer=bool(user_data.voice_answer),
            voice_type=getattr(user_data, "voice_type", "cat") or "cat",
            count_messages=user_data.count_messages,
        )

    def apply_to_user_data(self, user_data: Any) -> None:
        user_data.messages = self.messages
        user_data.count_messages = self.count_messages


@dataclass
class TextHandleResult:
    handled: bool = True
    early_reply: Optional[str] = None
    response_text: str = ""
    delivery_mode: ReplyDeliveryMode = ReplyDeliveryMode.NONE
    prefer_voice_out: bool = False
    mod_note_reply: Optional[str] = None
    persist_user_id: int = 0
    persist_chat_id: int = 0
    error_message: Optional[str] = None


@dataclass
class PhotoHandleResult:
    handled: bool = True
    early_reply: Optional[str] = None
    response_text: str = ""
    error_message: Optional[str] = None
    persist_user_id: int = 0
    persist_chat_id: int = 0
