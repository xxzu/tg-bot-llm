"""
NVIDIA API 服务模块（integrate.api.nvidia.com/v1/chat/completions）
"""
import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp
from dotenv import load_dotenv

from config.nvidia_models import NVIDIA_DEFAULT_MODEL_ID
from config.performance import CHAT_MAX_OUTPUT_TOKENS, NVIDIA_DISABLE_THINKING
from services.chat_history import slice_messages_for_api
from services.http_session import get_http_session

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

NVIDIA_DEFAULT_MODEL = NVIDIA_DEFAULT_MODEL_ID


def _cap_max_tokens(value: int, fast_chat: bool) -> int:
    if not fast_chat:
        return value
    return min(value, CHAT_MAX_OUTPUT_TOKENS)


def _nvidia_inference_fields(model_id: str, *, fast_chat: bool = True) -> Dict[str, Any]:
    """根据 model.yaml 生成请求参数；实现见 services.llm.adapters.nvidia_inference。"""
    from services.llm.adapters.nvidia_inference import nvidia_inference_fields

    return nvidia_inference_fields(model_id, fast_chat=fast_chat)


def _merge_messages_payload(
    system_instruction: str,
    user_data,
    prompt: str,
) -> List[dict]:
    messages: List[dict] = [{"role": "system", "content": system_instruction}]
    for msg in slice_messages_for_api(user_data.messages):
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})
    return messages


def _build_chat_payload(
    model_name: str,
    messages: List[dict],
    *,
    stream: bool,
    fast_chat: bool = True,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "stream": stream,
    }
    payload.update(_nvidia_inference_fields(model_name, fast_chat=fast_chat))
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
        # 部分模型在流结束时把正文放在 message 字段
        message = choice.get("message") or {}
        if isinstance(message, dict):
            final_content = (message.get("content") or "").strip()
            if final_content:
                yield final_content


async def iter_generate_text_with_nvidia(
    user_data,
    prompt: str,
    model: str = None,
    system_message: str = None,
) -> AsyncIterator[str]:
    if not NVIDIA_API_KEY:
        raise ValueError("NVIDIA_API_KEY 未配置，请在 .env 文件中设置")

    model_name = model or NVIDIA_DEFAULT_MODEL
    system_instruction = system_message or user_data.system_message or (
        "你是一个友好、专业、自然的喵喵助手。"
        "请用自然、流畅的语言回答问题，就像和朋友聊天一样。"
        "不需要在回复中提到模型名称或技术细节。"
        "直接回答问题，保持简洁明了。"
    )
    messages = _merge_messages_payload(system_instruction, user_data, prompt)
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = _build_chat_payload(model_name, messages, stream=True)

    session = await get_http_session()
    async with session.post(NVIDIA_API_URL, headers=headers, json=payload) as response:
        if response.status != 200:
            error_text = await response.text()
            logging.error(f"NVIDIA API 错误: {response.status} - {error_text}")
            raise Exception(f"NVIDIA API 请求失败: {response.status} - {error_text}")
        async for piece in _iter_sse_content(response):
            yield piece


async def generate_text_with_nvidia(
    user_data,
    prompt: str,
    model: str = None,
    system_message: str = None,
) -> str:
    parts = []
    async for piece in iter_generate_text_with_nvidia(
        user_data, prompt, model=model, system_message=system_message
    ):
        parts.append(piece)
    return "".join(parts)


async def generate_text_with_nvidia_stream(
    user_data,
    prompt: str,
    model: str = None,
    system_message: str = None,
) -> str:
    return await generate_text_with_nvidia(
        user_data, prompt, model=model, system_message=system_message
    )


async def process_image_with_nvidia(
    text: str,
    base64_image: str,
    model: str = None,
) -> str:
    if not NVIDIA_API_KEY:
        raise ValueError("NVIDIA_API_KEY 未配置，请在 .env 文件中设置")

    model_name = model or NVIDIA_DEFAULT_MODEL

    if "," in base64_image:
        image_url = base64_image
    else:
        image_url = f"data:image/jpeg;base64,{base64_image}"

    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text or "图片上有什么？请详细描述。"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
    ]

    infer = _nvidia_inference_fields(model_name, fast_chat=True)
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "max_tokens": min(infer.get("max_tokens", 4096), 1024),
        "temperature": infer.get("temperature", 0.7),
        "top_p": infer.get("top_p", 0.9),
        "stream": False,
    }
    if infer.get("chat_template_kwargs"):
        payload["chat_template_kwargs"] = infer["chat_template_kwargs"]

    session = await get_http_session()
    async with session.post(NVIDIA_API_URL, headers=headers, json=payload) as response:
        if response.status != 200:
            error_text = await response.text()
            logging.error(f"NVIDIA API 图片处理错误: {response.status} - {error_text}")
            raise Exception(f"NVIDIA API 图片处理失败: {response.status} - {error_text}")

        result = await response.json()
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        raise Exception("NVIDIA API 返回格式异常")


def is_nvidia_api_available() -> bool:
    return bool(NVIDIA_API_KEY)
