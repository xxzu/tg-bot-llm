"""Telegram 回复呈现（占位编辑、分片、语音状态）。"""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import Message

from services.application.dto import ReplyDeliveryMode
from utils.telegram_text import ensure_telegram_text, prepare_telegram_body


class ResponsePresenter:
    def __init__(self, message: Message, bot: Bot) -> None:
        self._message = message
        self._bot = bot
        self._chat_id = message.chat.id

    async def send_typing(self) -> None:
        await self._message.bot.send_chat_action(self._chat_id, action="typing")

    async def send_record_voice(self) -> None:
        await self._message.bot.send_chat_action(self._chat_id, action="record_voice")

    async def deliver_text(
        self,
        response_text: str,
        *,
        status_message: Optional[Message],
        delivery_mode: ReplyDeliveryMode,
    ) -> None:
        if delivery_mode == ReplyDeliveryMode.STREAM_ALREADY_SENT:
            return
        if not response_text.strip():
            return

        response_text = ensure_telegram_text(response_text)
        if status_message and len(response_text) <= 4096:
            body, parse_mode = prepare_telegram_body(response_text)
            try:
                if parse_mode == "HTML":
                    await status_message.edit_text(
                        body,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                else:
                    await status_message.edit_text(
                        body,
                        disable_web_page_preview=True,
                    )
                return
            except Exception:
                try:
                    await status_message.delete()
                except Exception:
                    pass
        elif status_message:
            try:
                await status_message.delete()
            except Exception:
                pass

        if len(response_text) > 4096:
            await self._send_long(response_text)
        else:
            await self._send_short(response_text)

    async def send_mod_note(self, note: str) -> None:
        await self._message.reply(f"🛡️ {note}")

    async def reply_plain(self, text: str) -> None:
        await self._message.reply(text)

    async def delete_status(self, status_message: Optional[Message]) -> None:
        if not status_message:
            return
        try:
            await status_message.delete()
        except Exception:
            pass

    async def _send_short(self, text: str) -> None:
        body, parse_mode = prepare_telegram_body(text)
        if parse_mode == "HTML":
            await self._message.reply(
                body,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        else:
            await self._message.reply(body, disable_web_page_preview=True)

    async def _send_long(self, text: str) -> None:
        content = ensure_telegram_text(text)
        lines = content.split("\n")
        chunk = ""
        chunks = []
        for line in lines:
            if len(chunk) + len(line) + 1 > 4096:
                chunks.append(chunk)
                chunk = line
            else:
                chunk = f"{chunk}{line}\n" if chunk else line
        if chunk:
            chunks.append(chunk)

        for i, part in enumerate(chunks):
            body, parse_mode = prepare_telegram_body(part)
            if i == 0:
                if parse_mode == "HTML":
                    await self._message.reply(
                        body,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                else:
                    await self._message.reply(body, disable_web_page_preview=True)
            else:
                if parse_mode == "HTML":
                    await self._message.answer(
                        body,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                else:
                    await self._message.answer(body, disable_web_page_preview=True)

    async def send_photo_answer(self, text: str, *, temp_message: Optional[Message]) -> None:
        if temp_message:
            try:
                await self._message.bot.delete_message(
                    self._chat_id, temp_message.message_id
                )
            except Exception as e:
                logging.warning("删除占位消息失败: %s", e)
        body, parse_mode = prepare_telegram_body(text)
        if parse_mode == "HTML":
            await self._message.answer(body, parse_mode=ParseMode.HTML)
        else:
            await self._message.answer(body)
