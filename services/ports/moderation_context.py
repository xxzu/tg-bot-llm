"""群管 tool 执行上下文（纯数据，无 aiogram）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ModerationToolContext:
    chat_id: int
    operator_user_id: int
    requester_is_admin: bool
    reply_message_id: Optional[int] = None
    reply_target_user_id: Optional[int] = None
    reply_text: Optional[str] = None
    can_moderate: bool = False

    @classmethod
    async def from_message(cls, message) -> "ModerationToolContext":
        from services.ports.moderation_mapping import build_tool_context_from_message

        return await build_tool_context_from_message(message)
