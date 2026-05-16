"""
从 models/llm_models.yaml 加载模型与提供商配置。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "models" / "llm_models.yaml"


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    kind: str
    api_key_env: str
    label: str
    base_url: str = ""
    extra_headers: Dict[str, str] = field(default_factory=dict)

    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "").strip()

    def is_available(self) -> bool:
        return bool(self.api_key())


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    display_name: str
    capabilities: Tuple[str, ...]
    key: str = ""
    menu: str = ""
    callback: str = ""
    button_label: str = ""
    inference_profile: str = ""
    inference: Dict[str, Any] = field(default_factory=dict)

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def menu_callback(self) -> str:
        if self.callback:
            return self.callback
        if self.menu == "nvidia" and self.key:
            return f"nvidia_{self.key}"
        if self.menu == "openrouter" and self.key:
            return f"openrouter_{self.key}"
        return self.key or self.id

    def selection_label(self, provider_label: str) -> str:
        return f"{provider_label} {self.display_name}"


@dataclass
class LLMRegistry:
    default_model_id: str
    providers: Dict[str, ProviderSpec]
    models_by_id: Dict[str, ModelSpec]
    models_by_callback: Dict[str, ModelSpec]
    inference_profiles: Dict[str, Dict[str, Any]]
    menus: Dict[str, Dict[str, Any]]

    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        if not model_id:
            return None
        return self.models_by_id.get(model_id)

    def get_model_by_callback(self, callback_data: str) -> Optional[ModelSpec]:
        return self.models_by_callback.get(callback_data)

    def list_menu_models(self, menu_name: str) -> List[ModelSpec]:
        return [m for m in self.models_by_id.values() if m.menu == menu_name]

    def provider_for(self, model_id: str) -> Optional[ProviderSpec]:
        spec = self.get_model(model_id)
        if not spec:
            return None
        return self.providers.get(spec.provider)

    def is_model_available(self, model_id: str) -> bool:
        spec = self.get_model(model_id)
        if not spec:
            return False
        prov = self.providers.get(spec.provider)
        return bool(prov and prov.is_available())

    def inference_payload(self, spec: ModelSpec, *, fast_chat: bool = True) -> Dict[str, Any]:
        from config.performance import CHAT_MAX_OUTPUT_TOKENS, NVIDIA_DISABLE_THINKING

        fields: Dict[str, Any] = {}
        if spec.inference:
            fields = dict(spec.inference)
        elif spec.inference_profile:
            fields = dict(self.inference_profiles.get(spec.inference_profile, {}))

        if spec.provider == "openrouter" and "max_tokens" not in fields:
            fields["max_tokens"] = CHAT_MAX_OUTPUT_TOKENS

        if spec.provider == "nvidia":
            from services.llm.adapters.nvidia_inference import nvidia_inference_fields

            # YAML 未写 profile 时按 model id 模式回退
            if not fields:
                fields = nvidia_inference_fields(spec.id, fast_chat=fast_chat)
            elif fast_chat and NVIDIA_DISABLE_THINKING:
                fields = dict(fields)
                fields.pop("chat_template_kwargs", None)
                fields.pop("reasoning_budget", None)
            if fast_chat and "max_tokens" in fields:
                fields["max_tokens"] = min(
                    int(fields["max_tokens"]), CHAT_MAX_OUTPUT_TOKENS
                )

        return fields


def _load_yaml() -> Dict[str, Any]:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_registry(data: Dict[str, Any]) -> LLMRegistry:
    providers: Dict[str, ProviderSpec] = {}
    for name, p in (data.get("providers") or {}).items():
        providers[name] = ProviderSpec(
            name=name,
            kind=p.get("kind", "openai_chat"),
            api_key_env=p.get("api_key_env", ""),
            label=p.get("label", name),
            base_url=p.get("base_url", ""),
            extra_headers=dict(p.get("extra_headers") or {}),
        )

    models_by_id: Dict[str, ModelSpec] = {}
    models_by_callback: Dict[str, ModelSpec] = {}

    for raw in data.get("models") or []:
        caps = tuple(raw.get("capabilities") or ["chat"])
        spec = ModelSpec(
            id=raw["id"],
            key=raw.get("key", ""),
            provider=raw["provider"],
            menu=raw.get("menu", ""),
            callback=raw.get("callback", ""),
            display_name=raw.get("display_name", raw["id"]),
            button_label=raw.get("button_label") or raw.get("display_name", raw["id"]),
            capabilities=caps,
            inference_profile=raw.get("inference_profile", ""),
            inference=dict(raw.get("inference") or {}),
        )
        models_by_id[spec.id] = spec
        cb = spec.menu_callback()
        if cb:
            models_by_callback[cb] = spec

    return LLMRegistry(
        default_model_id=data.get("default_model_id", ""),
        providers=providers,
        models_by_id=models_by_id,
        models_by_callback=models_by_callback,
        inference_profiles=dict(data.get("inference_profiles") or {}),
        menus=dict(data.get("menus") or {}),
    )


@lru_cache(maxsize=1)
def get_registry() -> LLMRegistry:
    return _build_registry(_load_yaml())


def reload_registry() -> LLMRegistry:
    get_registry.cache_clear()
    return get_registry()
