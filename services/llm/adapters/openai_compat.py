"""OpenAI Chat Completions 兼容适配（NVIDIA / OpenRouter）。"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp

from services.http_session import get_http_session
from services.llm.messages import build_chat_messages_from_request
from services.llm.registry import LLMRegistry, ModelSpec, ProviderSpec
from services.llm.types import LLMChatRequest, LLMVisionRequest
from services.moderation_tools import OPENAI_MODERATION_TOOLS, execute_tool
from services.ports.moderation_context import ModerationToolContext
from utils.telegram_text import ensure_telegram_text

logger = logging.getLogger(__name__)


def _auth_headers(provider: ProviderSpec) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {provider.api_key()}",
        "Content-Type": "application/json",
    }
    headers.update(provider.extra_headers)
    return headers


def _build_payload(
    registry: LLMRegistry,
    spec: ModelSpec,
    messages: List[dict],
    *,
    stream: bool,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": spec.id,
        "messages": messages,
        "stream": stream,
    }
    payload.update(registry.inference_payload(spec))
    return payload


async def _iter_sse_content(response: aiohttp.ClientResponse) -> AsyncIterator[str]:
    async for raw in response.content:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if "choices" not in chunk or not chunk["choices"]:
            continue
        choice = chunk["choices"][0]
        delta = choice.get("delta", {}) or {}
        content = delta.get("content") or ""
        if content:
            yield content
            continue
        message = choice.get("message") or {}
        if isinstance(message, dict):
            final_content = (message.get("content") or "").strip()
            if final_content:
                yield final_content


def _is_openrouter(provider: ProviderSpec) -> bool:
    return provider.name == "openrouter" or "openrouter.ai" in (provider.base_url or "")


async def _post_json(
    api_url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    *,
    provider: Optional[ProviderSpec] = None,
    model_id: str = "",
) -> Dict[str, Any]:
    from config.performance import OPENROUTER_API_RETRIES

    retries = OPENROUTER_API_RETRIES if provider and _is_openrouter(provider) else 0
    session = await get_http_session()
    t0 = time.monotonic()
    last_body = ""
    for attempt in range(retries + 1):
        async with session.post(api_url, headers=headers, json=payload) as response:
            last_body = await response.text()
            if response.status == 200:
                if provider and _is_openrouter(provider):
                    logger.info(
                        "OpenRouter 完成 model=%s 耗时=%.2fs stream=%s",
                        model_id or payload.get("model"),
                        time.monotonic() - t0,
                        payload.get("stream"),
                    )
                return json.loads(last_body)
            if (
                response.status == 429
                and provider
                and _is_openrouter(provider)
                and attempt < retries
            ):
                wait = 2.0 * (attempt + 1)
                logger.warning(
                    "OpenRouter 429 限流 model=%s，%ss 后重试 (%s/%s)",
                    model_id or payload.get("model"),
                    wait,
                    attempt + 1,
                    retries,
                )
                await asyncio.sleep(wait)
                continue
            raise RuntimeError(f"API {response.status}: {last_body[:500]}")
    raise RuntimeError(f"API failed: {last_body[:500]}")


async def complete(
    registry: LLMRegistry,
    provider: ProviderSpec,
    spec: ModelSpec,
    request: LLMChatRequest,
) -> str:
    messages = build_chat_messages_from_request(request)
    payload = _build_payload(registry, spec, messages, stream=False)
    result = await _post_json(
        provider.base_url,
        _auth_headers(provider),
        payload,
        provider=provider,
        model_id=spec.id,
    )
    if "choices" in result and result["choices"]:
        return ensure_telegram_text(result["choices"][0]["message"].get("content"))
    raise RuntimeError("API 返回格式异常")


async def iter_complete(
    registry: LLMRegistry,
    provider: ProviderSpec,
    spec: ModelSpec,
    request: LLMChatRequest,
) -> AsyncIterator[str]:
    messages = build_chat_messages_from_request(request)
    headers = _auth_headers(provider)
    headers["Accept"] = "text/event-stream"
    payload = _build_payload(registry, spec, messages, stream=True)

    from config.performance import OPENROUTER_API_RETRIES

    session = await get_http_session()
    retries = OPENROUTER_API_RETRIES if _is_openrouter(provider) else 0
    t0 = time.monotonic()
    first_token_logged = False
    for attempt in range(retries + 1):
        async with session.post(
            provider.base_url, headers=headers, json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                if (
                    response.status == 429
                    and _is_openrouter(provider)
                    and attempt < retries
                ):
                    wait = 2.0 * (attempt + 1)
                    logger.warning(
                        "OpenRouter 流式 429 model=%s，%ss 后重试",
                        spec.id,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(
                    "OpenAI-compat API %s: %s", response.status, error_text[:300]
                )
                raise RuntimeError(f"API 请求失败: {response.status}")
            async for piece in _iter_sse_content(response):
                if (
                    not first_token_logged
                    and _is_openrouter(provider)
                    and piece
                ):
                    logger.info(
                        "OpenRouter 首 token model=%s TTFT=%.2fs",
                        spec.id,
                        time.monotonic() - t0,
                    )
                    first_token_logged = True
                yield piece
            if _is_openrouter(provider):
                logger.info(
                    "OpenRouter 流式结束 model=%s 总耗时=%.2fs",
                    spec.id,
                    time.monotonic() - t0,
                )
            return


async def complete_with_tools(
    registry: LLMRegistry,
    provider: ProviderSpec,
    spec: ModelSpec,
    request: LLMChatRequest,
    tool_ctx: ModerationToolContext,
    *,
    max_tool_rounds: int = 3,
) -> str:
    messages = build_chat_messages_from_request(request)
    headers = _auth_headers(provider)
    extra = dict(registry.inference_payload(spec))
    extra["stream"] = False

    working = list(messages)
    for round_i in range(max_tool_rounds):
        payload = {
            "model": spec.id,
            "messages": working,
            "tools": OPENAI_MODERATION_TOOLS,
            "tool_choice": "auto",
            **extra,
        }
        result = await _post_json(
            provider.base_url, headers, payload, provider=provider, model_id=spec.id
        )
        msg = (result.get("choices") or [{}])[0].get("message") or {}
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            working.append(msg)
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments") or "{}"
                tid = tc.get("id") or f"call_{round_i}"
                tool_out = await execute_tool(name, raw_args, tool_ctx)
                working.append(
                    {"role": "tool", "tool_call_id": tid, "content": tool_out}
                )
            continue
        content = msg.get("content")
        if content:
            return str(content).strip()
        if round_i == max_tool_rounds - 1:
            break
        working.append(
            {
                "role": "user",
                "content": "请用简短中文回复用户；若已执法完毕请说明结果。",
            }
        )
    return ""


async def vision(
    registry: LLMRegistry,
    provider: ProviderSpec,
    spec: ModelSpec,
    request: LLMVisionRequest,
) -> str:
    if "," in request.image_base64:
        image_url = request.image_base64
    else:
        image_url = f"data:image/jpeg;base64,{request.image_base64}"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": request.prompt or "图片上有什么？请详细描述。"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
    ]
    infer = registry.inference_payload(spec)
    payload: Dict[str, Any] = {
        "model": spec.id,
        "messages": messages,
        "max_tokens": min(int(infer.get("max_tokens", 4096)), 1024),
        "temperature": infer.get("temperature", 0.7),
        "top_p": infer.get("top_p", 0.9),
        "stream": False,
    }
    if infer.get("chat_template_kwargs"):
        payload["chat_template_kwargs"] = infer["chat_template_kwargs"]

    result = await _post_json(
        provider.base_url,
        _auth_headers(provider),
        payload,
        provider=provider,
        model_id=spec.id,
    )
    if "choices" in result and result["choices"]:
        return result["choices"][0]["message"]["content"]
    raise RuntimeError("API 返回格式异常")
