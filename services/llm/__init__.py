"""LLM 统一调用层（invoker 延迟导入，避免与 config.buttons 循环依赖）。"""
from services.llm.registry import LLMRegistry, ModelSpec, ProviderSpec, get_registry
from services.llm.types import LLMChatRequest, LLMChatResult, LLMVisionRequest


def get_invoker():
    from services.llm.invoker import get_invoker as _get

    return _get()


__all__ = [
    "LLMChatRequest",
    "LLMChatResult",
    "LLMVisionRequest",
    "ModelSpec",
    "ProviderSpec",
    "LLMRegistry",
    "get_invoker",
    "get_registry",
]
