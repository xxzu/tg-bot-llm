"""Google Gemini 原生 API 适配。"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from services.chat_history import slice_messages_for_api
from services.llm.types import LLMChatRequest
from utils.telegram_text import ensure_telegram_text

logger = logging.getLogger(__name__)


def _build_gemini_contents(system_instruction: str, user_data, prompt: str) -> str:
    history_slice = slice_messages_for_api(user_data.messages)
    if not history_slice:
        return f"{system_instruction}\n\n用户: {prompt}"
    history_text = ""
    for msg in history_slice:
        role = "用户" if msg["role"] == "user" else "助手"
        history_text += f"{role}: {msg['content']}\n\n"
    return f"{system_instruction}\n\n{history_text}用户: {prompt}"


async def complete(request: LLMChatRequest) -> str:
    from config.performance import CHAT_MAX_OUTPUT_TOKENS
    from services.gemini import USE_NEW_API, client, genai_old

    contents = _build_gemini_contents(
        request.system_instruction, request.user_data, request.prompt
    )
    model_id = request.model_id

    if USE_NEW_API and client is not None:
        response_gemini = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model=model_id,
                contents=contents,
                config={"max_output_tokens": CHAT_MAX_OUTPUT_TOKENS},
            )
        )
        return ensure_telegram_text(response_gemini.text)

    model = genai_old.GenerativeModel(
        model_id, system_instruction=request.system_instruction
    )
    response_gemini = await asyncio.to_thread(lambda: model.generate_content(contents))
    return ensure_telegram_text(response_gemini.text)


async def iter_complete(request: LLMChatRequest) -> AsyncIterator[str]:
    text = await complete(request)
    if text:
        yield text
