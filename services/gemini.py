"""
Gemini API 服务模块
"""
import asyncio
import base64
import logging
import os

from aiogram.client.session import aiohttp
from dotenv import load_dotenv

from config.performance import CHAT_MAX_OUTPUT_TOKENS
from services.chat_history import slice_messages_for_api
from utils.telegram_text import ensure_telegram_text

# 加载环境变量
load_dotenv()

# Gemini API 密钥
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini SDK 兼容
try:
    from google import genai as genai_new
except Exception:
    genai_new = None

try:
    import google.generativeai as genai_old
except Exception:
    genai_old = None

# 初始化 Gemini 客户端
client = None
USE_NEW_API = False

# 优先使用新 SDK
if genai_new is not None and hasattr(genai_new, "Client") and genai_new.Client is not None:
    try:
        client = genai_new.Client(api_key=GEMINI_API_KEY)
        USE_NEW_API = True
    except Exception as e:
        logging.warning(f"初始化 google.genai 失败，将回退到旧 SDK: {e}")
        client = None
        USE_NEW_API = False

# 旧 SDK 配置
if not USE_NEW_API:
    if genai_old is None:
        raise ImportError("google.generativeai 不可用，且 google.genai 初始化失败，无法使用 Gemini")
    genai_old.configure(api_key=GEMINI_API_KEY)


async def download_and_encode_image(url: str) -> str:
    """下载并编码图片为 base64"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                image_content = await resp.read()
                base64_image = base64.b64encode(image_content).decode("utf-8")
                return f"data:image/jpeg;base64,{base64_image}"
    raise ValueError("Failed to download image")


async def process_image_with_gemini(text: str, base64_image: str) -> str:
    """使用 Gemini API 处理图片理解"""
    try:
        from PIL import Image as PILImage
    except ImportError:
        import PIL.Image as PILImage
    import io
    
    # 解码 base64 图片
    image_data = base64.b64decode(base64_image.split(",")[1] if "," in base64_image else base64_image)
    image = PILImage.open(io.BytesIO(image_data))
    
    if USE_NEW_API and client is not None:
        try:
            model_names = ["gemini-1.5-pro-latest", "gemini-1.5-flash-latest", "gemini-1.5-pro"]
            response = None
            last_error = None
            
            for model_name in model_names:
                try:
                    response = await asyncio.to_thread(
                        lambda m=model_name: client.models.generate_content(
                            model=m,
                            contents=[text, image]
                        )
                    )
                    break
                except Exception as e:
                    last_error = e
                    logging.warning(f"尝试模型 {model_name} 失败: {e}")
                    continue
            
            if response:
                return response.text
            else:
                logging.warning("新 API 所有模型都失败，回退到旧 API")
                raise Exception("新 API 失败")
        except Exception as e:
            logging.warning(f"新 API 失败，回退到旧 API: {e}")
            model = genai_old.GenerativeModel("gemini-1.5-pro")
            response = await asyncio.to_thread(
                lambda: model.generate_content([text, image])
            )
            return response.text
    else:
        model = genai_old.GenerativeModel("gemini-1.5-pro")
        response = await asyncio.to_thread(
            lambda: model.generate_content([text, image])
        )
        return response.text


async def generate_text_response(user_data, promt: str) -> str:
    """生成文本响应"""
    # 获取系统提示词
    system_instruction = user_data.system_message if user_data.system_message else (
        "你是一个友好、专业、自然的喵喵助手。"
        "请用自然、流畅的语言回答问题，就像和朋友聊天一样。"
        "不需要在回复中提到模型名称或技术细节。"
        "直接回答问题，保持简洁明了。"
    )

    # 构建包含聊天历史的完整对话内容（滑动窗口与 API 一致）
    history_slice = slice_messages_for_api(user_data.messages)
    if not history_slice:
        contents = f"{system_instruction}\n\n用户: {promt}"
    else:
        history_text = ""
        for msg in history_slice:
            role = "用户" if msg["role"] == "user" else "助手"
            history_text += f"{role}: {msg['content']}\n\n"
        contents = f"{system_instruction}\n\n{history_text}用户: {promt}"

    if USE_NEW_API and client is not None:
        response_gemini = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model=user_data.model,
                contents=contents,
                config={"max_output_tokens": CHAT_MAX_OUTPUT_TOKENS},
            )
        )
        return ensure_telegram_text(response_gemini.text)
    else:
        model = genai_old.GenerativeModel(user_data.model, system_instruction=system_instruction)
        response_gemini = await asyncio.to_thread(
            lambda: model.generate_content(contents)
        )
        return ensure_telegram_text(response_gemini.text)
