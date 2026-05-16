"""
OpenRouter API 服务模块
使用 OpenRouter API 进行文本生成
"""
import json
import logging
import asyncio

import aiohttp

from config.performance import CHAT_MAX_OUTPUT_TOKENS
from config.settings import OPENROUTER_API_KEY
from services.chat_history import slice_messages_for_api
from services.http_session import get_http_session
from utils.telegram_text import ensure_telegram_text


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# 默认模型
OPENROUTER_DEFAULT_MODEL = "arcee-ai/trinity-large-preview:free"


async def generate_text_with_openrouter(
    user_data,
    prompt: str,
    model: str = None,
    system_message: str = None
) -> str:
    """
    使用 OpenRouter API 生成文本响应
    
    Args:
        user_data: 用户数据对象
        prompt: 用户输入的文本
        model: 可选的模型名称
        system_message: 可选的系统提示词
    
    Returns:
        AI 生成的响应文本
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY 未配置，请在 .env 文件中设置")
    
    model_name = model or OPENROUTER_DEFAULT_MODEL
    
    # 获取系统提示词
    system_instruction = system_message or user_data.system_message or (
        "你是一个友好、专业、自然的喵喵助手。"
        "请用自然、流畅的语言回答问题，就像和朋友聊天一样。"
        "不需要在回复中提到模型名称或技术细节。"
        "直接回答问题，保持简洁明了。"
    )
    
    # 构建消息列表
    messages = [{"role": "system", "content": system_instruction}]
    
    for msg in slice_messages_for_api(user_data.messages):
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # 添加当前用户消息
    messages.append({"role": "user", "content": prompt})
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gemini-tg-bot", # OpenRouter 要求
        "X-Title": "Gemini Telegram Bot" # OpenRouter 要求
    }
    
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": CHAT_MAX_OUTPUT_TOKENS,
        "stream": False,
    }

    try:
        session = await get_http_session()
        async with session.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logging.error(f"OpenRouter API 错误: {response.status} - {error_text}")
                raise Exception(f"OpenRouter API 请求失败: {response.status} - {error_text}")

            result = await response.json()

            if "choices" in result and len(result["choices"]) > 0:
                return ensure_telegram_text(
                    result["choices"][0]["message"].get("content")
                )
            if "error" in result:
                raise Exception(f"OpenRouter API返回错误: {result['error']}")
            raise Exception("OpenRouter API 返回格式异常")
                    
    except asyncio.TimeoutError:
        raise Exception("OpenRouter API 请求超时，请检查网络连接或稍后重试")
    except aiohttp.ClientError as e:
        raise Exception(f"OpenRouter API 网络错误: {e}")


async def generate_text_with_openrouter_stream(
    user_data,
    prompt: str,
    model: str = None
) -> str:
    """
    使用 OpenRouter API 流式生成文本响应
    
    Args:
        user_data: 用户数据对象
        prompt: 用户输入的文本
        model: 可选的模型名称
    
    Returns:
        AI 生成的完整响应文本
    """
    if not OPENROUTER_API_KEY:
         raise ValueError("OPENROUTER_API_KEY 未配置，请在 .env 文件中设置")
    
    model_name = model or OPENROUTER_DEFAULT_MODEL
    
    system_instruction = user_data.system_message if user_data.system_message else (
        "你是一个友好、专业、自然的喵喵助手。"
        "请用自然、流畅的语言回答问题，就像和朋友聊天一样。"
        "不需要在回复中提到模型名称或技术细节。"
        "直接回答问题，保持简洁明了。"
    )
    
    messages = [{"role": "system", "content": system_instruction}]
    
    for msg in slice_messages_for_api(user_data.messages):
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    messages.append({"role": "user", "content": prompt})
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gemini-tg-bot",
        "X-Title": "Gemini Telegram Bot"
    }
    
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": CHAT_MAX_OUTPUT_TOKENS,
        "stream": True,
    }

    full_response = ""

    try:
        session = await get_http_session()
        async with session.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logging.error(f"OpenRouter API 错误: {response.status} - {error_text}")
                raise Exception(f"OpenRouter API 请求失败: {response.status} - {error_text}")

            buffer = ""
            async for line in response.content:
                line = line.decode("utf-8")
                buffer += line

                while "\n" in buffer:
                    line_end = buffer.find("\n")
                    line_content = buffer[:line_end].strip()
                    buffer = buffer[line_end + 1:]

                    if line_content.startswith("data: "):
                        data = line_content[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_response += content
                        except json.JSONDecodeError:
                            continue

    except asyncio.TimeoutError:
        raise Exception("OpenRouter API 请求超时，请检查网络连接或稍后重试")
    except aiohttp.ClientError as e:
        raise Exception(f"OpenRouter API 网络错误: {e}")
    
    return full_response


# OpenRouter 模型列表
OPENROUTER_MODELS = [
    ("arcee-ai/trinity-large-preview:free", "Trinity (Free)"),
]
