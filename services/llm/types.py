"""LLM 调用层公共类型（业务层仅依赖本模块与 invoker）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class LLMChatRequest:
    model_id: str
    user_data: Any
    prompt: str
    system_instruction: str


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
