"""构建 OpenAI 风格 messages 列表。"""
from __future__ import annotations

from typing import List

from services.chat_history import slice_messages_for_api
from services.llm.conversation import ConversationSnapshot
from services.llm.types import LLMChatRequest


def build_chat_messages_from_request(request: LLMChatRequest) -> List[dict]:
    return build_chat_messages(
        request.system_instruction,
        request.conversation,
        request.prompt,
    )


def build_messages_payload(
    system_instruction: str,
    user_data,
    prompt: str,
) -> List[dict]:
    """兼容旧签名（chat_tools 等）。"""
    return build_chat_messages(
        system_instruction,
        ConversationSnapshot.from_user_data(user_data),
        prompt,
    )


def build_chat_messages(
    system_instruction: str,
    conversation: ConversationSnapshot,
    prompt: str,
) -> List[dict]:
    messages: List[dict] = [{"role": "system", "content": system_instruction}]
    for msg in slice_messages_for_api(conversation.messages):
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})
    return messages
