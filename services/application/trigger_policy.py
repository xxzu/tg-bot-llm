"""群聊触发策略（纯规则，无 Telegram API）。"""
from __future__ import annotations

from services.application.dto import IncomingChatContext


def evaluate_group_trigger(ctx: IncomingChatContext) -> bool:
    if ctx.chat_type not in ("group", "supergroup"):
        return True
    if ctx.is_reply_to_bot:
        return True
    if ctx.is_mention and (ctx.message_text or ctx.has_voice):
        return True
    if ctx.has_wake_word:
        return True
    return False
