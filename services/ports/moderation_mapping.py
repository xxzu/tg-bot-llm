"""Telegram Message → ModerationToolContext（仅接口层）。"""
from __future__ import annotations

from aiogram.types import Message

from services.ports.moderation_context import ModerationToolContext
from services.ports.moderation_port import get_moderation_port


async def build_tool_context_from_message(message: Message) -> ModerationToolContext:
    chat_id = message.chat.id
    operator = message.from_user.id if message.from_user else 0
    port = get_moderation_port()
    requester_is_admin = await port.is_user_group_admin(chat_id, operator)
    caps = await port.get_group_capabilities(chat_id)

    reply = message.reply_to_message
    reply_mid = reply.message_id if reply else None
    reply_uid = None
    reply_text = None
    if reply and reply.from_user:
        reply_uid = reply.from_user.id
        reply_text = (reply.text or reply.caption or "").strip() or None

    return ModerationToolContext(
        chat_id=chat_id,
        operator_user_id=operator,
        requester_is_admin=requester_is_admin,
        reply_message_id=reply_mid,
        reply_target_user_id=reply_uid,
        reply_text=reply_text,
        can_moderate=bool(caps.get("can_moderate")),
    )
