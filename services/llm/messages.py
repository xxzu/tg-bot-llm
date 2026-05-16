"""构建 OpenAI 风格 messages 列表。"""
from __future__ import annotations

from typing import Any, List

from services.chat_history import slice_messages_for_api


def build_chat_messages(
    system_instruction: str,
    user_data: Any,
    prompt: str,
) -> List[dict]:
    messages: List[dict] = [{"role": "system", "content": system_instruction}]
    for msg in slice_messages_for_api(user_data.messages):
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})
    return messages
