"""
将模型流式输出实时更新到 Telegram 占位消息。
"""
import time
from typing import AsyncIterator

from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ParseMode
from aiogram.types import Message

from config.performance import STREAM_EDIT_INTERVAL_SEC
from config.text import pick_thinking_status
from services.moderation_actions import parse_and_strip_mod_tags
from utils.telegram_text import EMPTY_REPLY_FALLBACK, ensure_telegram_text, prepare_telegram_body


async def _edit_placeholder(placeholder: Message, text: str) -> bool:
    body, parse_mode = prepare_telegram_body(text)
    if not body.strip():
        return False
    try:
        if parse_mode == "HTML":
            await placeholder.edit_text(
                body,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        else:
            await placeholder.edit_text(body, disable_web_page_preview=True)
        return True
    except TelegramBadRequest:
        return False


async def stream_to_telegram_message(
    message: Message,
    text_chunks: AsyncIterator[str],
) -> str:
    """
    用占位消息展示流式生成；返回完整文本（已 strip，可能为空）。
    """
    placeholder = await message.reply(pick_thinking_status())
    full = ""
    last_edit = 0.0
    first_edit = True

    async for piece in text_chunks:
        if not piece:
            continue
        full += piece
        if not full.strip():
            continue
        now = time.monotonic()
        if not first_edit and now - last_edit < STREAM_EDIT_INTERVAL_SEC:
            continue
        await _edit_placeholder(placeholder, full[:4096])
        last_edit = now
        first_edit = False

    full, _ = parse_and_strip_mod_tags(full)
    full = full.strip()
    if full:
        await _edit_placeholder(placeholder, full[:4096])
    else:
        try:
            await placeholder.delete()
        except TelegramBadRequest:
            pass

    return full


async def stream_to_telegram_message_or_fallback(
    message: Message,
    text_chunks: AsyncIterator[str],
) -> str:
    """流式展示；若无任何正文则发送兜底文案。"""
    full = await stream_to_telegram_message(message, text_chunks)
    if full.strip():
        return full
    fallback = EMPTY_REPLY_FALLBACK
    await message.reply(fallback)
    return fallback
