"""
统一 LLM 调用入口。业务层只依赖本模块，不直接引用 nvidia/openrouter/gemini 服务。
"""
from __future__ import annotations

from typing import AsyncIterator, Optional

from services.llm.adapters import gemini_adapter, openai_compat
from services.llm.registry import LLMRegistry, ModelSpec, get_registry
from services.llm.types import LLMChatRequest, LLMVisionRequest
from services.ports.moderation_context import ModerationToolContext


class LLMInvoker:
    def __init__(self, registry: Optional[LLMRegistry] = None) -> None:
        self._registry = registry or get_registry()

    @property
    def registry(self) -> LLMRegistry:
        return self._registry

    def resolve(self, model_id: str) -> Optional[ModelSpec]:
        return self._registry.get_model(model_id)

    def is_available(self, model_id: str) -> bool:
        return self._registry.is_model_available(model_id)

    def unavailable_reason(self, model_id: str) -> str:
        spec = self.resolve(model_id)
        if not spec:
            return f"模型未在配置中注册: {model_id}"
        prov = self._registry.providers.get(spec.provider)
        if not prov:
            return f"未知提供商: {spec.provider}"
        if not prov.is_available():
            return f"{prov.label} API 未配置（环境变量 {prov.api_key_env}）"
        return ""

    async def chat(self, request: LLMChatRequest) -> str:
        spec = self._require_model(request.model_id)
        prov = self._require_provider(spec)
        self._require_available(spec, prov)

        if prov.kind == "gemini":
            return await gemini_adapter.complete(request)
        return await openai_compat.complete(self._registry, prov, spec, request)

    async def iter_chat(self, request: LLMChatRequest) -> AsyncIterator[str]:
        spec = self._require_model(request.model_id)
        prov = self._require_provider(spec)
        self._require_available(spec, prov)

        if prov.kind == "gemini":
            async for piece in gemini_adapter.iter_complete(request):
                yield piece
            return

        async for piece in openai_compat.iter_complete(
            self._registry, prov, spec, request
        ):
            yield piece

    async def chat_with_tools(
        self,
        request: LLMChatRequest,
        tool_ctx: ModerationToolContext,
    ) -> str:
        spec = self._require_model(request.model_id)
        if not spec.supports("tools"):
            raise ValueError(f"模型 {spec.id} 不支持 function calling")
        prov = self._require_provider(spec)
        self._require_available(spec, prov)
        if prov.kind == "gemini":
            raise ValueError("Gemini 暂不支持群管 tools")
        return await openai_compat.complete_with_tools(
            self._registry, prov, spec, request, tool_ctx
        )

    async def vision(self, request: LLMVisionRequest) -> str:
        spec = self._require_model(request.model_id)
        if not spec.supports("vision"):
            raise ValueError(f"模型 {spec.id} 不支持视觉")
        prov = self._require_provider(spec)
        self._require_available(spec, prov)

        if prov.kind == "gemini":
            from services.gemini import process_image_with_gemini

            return await process_image_with_gemini(request.prompt, request.image_base64)

        return await openai_compat.vision(self._registry, prov, spec, request)

    def _require_model(self, model_id: str) -> ModelSpec:
        spec = self.resolve(model_id)
        if not spec:
            raise ValueError(self.unavailable_reason(model_id))
        return spec

    def _require_provider(self, spec: ModelSpec):
        prov = self._registry.providers.get(spec.provider)
        if not prov:
            raise ValueError(f"未知提供商: {spec.provider}")
        return prov

    def _require_available(self, spec: ModelSpec, prov) -> None:
        if not prov.is_available():
            raise ValueError(f"{prov.label} API 未配置（{prov.api_key_env}）")


_invoker: Optional[LLMInvoker] = None


def get_invoker() -> LLMInvoker:
    global _invoker
    if _invoker is None:
        _invoker = LLMInvoker()
    return _invoker
