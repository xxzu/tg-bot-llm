"""LLM 调用层公共类型（业务层仅依赖本模块与 invoker）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from services.llm.conversation import ConversationSnapshot


@dataclass
class LLMChatRequest:
    model_id: str
    prompt: str
    system_instruction: str
    conversation: Optional[ConversationSnapshot] = None
    user_data: Optional[Any] = None

    def __post_init__(self) -> None:
        if self.conversation is None and self.user_data is not None:
            self.conversation = ConversationSnapshot.from_user_data(self.user_data)
        if self.conversation is None:
            self.conversation = ConversationSnapshot(messages=[])


@dataclass
class LLMVisionRequest:
    model_id: str
    prompt: str
    image_base64: str


@dataclass
class LLMChatResult:
    text: str
    model_id: str = ""


Capability = str  # chat | stream | tools | vision
