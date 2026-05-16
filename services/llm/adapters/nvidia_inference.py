"""NVIDIA 推理参数（model.yaml 对齐；无 YAML profile 时回退）。"""
from __future__ import annotations

from typing import Any, Dict

from config.performance import CHAT_MAX_OUTPUT_TOKENS, NVIDIA_DISABLE_THINKING


def _cap_max_tokens(value: int, fast_chat: bool) -> int:
    if not fast_chat:
        return value
    return min(value, CHAT_MAX_OUTPUT_TOKENS)


def nvidia_inference_fields(model_id: str, *, fast_chat: bool = True) -> Dict[str, Any]:
    mid = model_id.lower()
    no_think = fast_chat and NVIDIA_DISABLE_THINKING

    if mid.startswith("z-ai/glm"):
        fields = {
            "max_tokens": 16384,
            "temperature": 1.0,
            "top_p": 1.0,
            "chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False},
        }
    elif mid.startswith("minimaxai/"):
        fields = {"max_tokens": 8192, "temperature": 1.0, "top_p": 0.95}
    elif mid.startswith("stepfun-ai/"):
        fields = {"max_tokens": 16384, "temperature": 1.0, "top_p": 0.9}
    elif "nemotron" in mid:
        fields = {
            "max_tokens": 16384,
            "temperature": 1.0,
            "top_p": 0.95,
            "chat_template_kwargs": {"thinking": True},
            "reasoning_budget": 16384,
        }
    elif mid.startswith("openai/gpt-oss"):
        fields = {"max_tokens": 4096, "temperature": 1.0, "top_p": 1.0}
    elif "qwen3-next" in mid:
        fields = {"max_tokens": 4096, "temperature": 0.6, "top_p": 0.7}
    elif "deepseek-v4-flash" in mid:
        fields = {
            "max_tokens": 16384,
            "temperature": 1.0,
            "top_p": 0.95,
            "chat_template_kwargs": {
                "thinking": True,
                "reasoning_effort": "high",
            },
        }
    elif "kimi" in mid:
        fields = {
            "max_tokens": 16384,
            "temperature": 1.0,
            "top_p": 1.0,
            "chat_template_kwargs": {"thinking": True},
        }
    elif "deepseek" in mid:
        fields = {
            "max_tokens": 16384,
            "temperature": 1.0,
            "top_p": 0.95,
            "chat_template_kwargs": {"thinking": True},
        }
    else:
        fields = {"max_tokens": 16384, "temperature": 0.7, "top_p": 0.9}

    if no_think:
        fields.pop("chat_template_kwargs", None)
        fields.pop("reasoning_budget", None)

    fields["max_tokens"] = _cap_max_tokens(fields.get("max_tokens", 4096), fast_chat)
    return fields
