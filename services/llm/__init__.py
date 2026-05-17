"""LLM 统一调用层（invoker 延迟导入，避免与 config.buttons 循环依赖）。"""
from services.llm.registry import (
    LLMRegistry,
    ModelSpec,
    ProviderSpec,
    default_model_for_session,
    get_registry,
    resolve_vision_model_id,
)
from services.llm.conversation import ConversationSnapshot
from services.llm.types import LLMChatRequest, LLMChatResult, LLMVisionRequest


def get_invoker():
    from services.llm.invoker import get_invoker as _get

    return _get()


__all__ = [
    "ConversationSnapshot",
    "LLMChatRequest",
    "LLMChatResult",
    "LLMVisionRequest",
    "ModelSpec",
    "ProviderSpec",
    "LLMRegistry",
    "default_model_for_session",
    "resolve_vision_model_id",
    "get_invoker",
    "get_registry",
]
