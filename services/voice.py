"""
语音处理服务模块
使用 edge-tts (免费) 进行文字转语音
"""
import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import edge_tts
from aiogram import Bot, types
from aiogram.types import FSInputFile
from dotenv import load_dotenv
from pydub import AudioSegment

# 加载环境变量
load_dotenv()

# OpenAI API 密钥（用于语音转文字，可选）
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = None
if openai_api_key:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=openai_api_key)
    except Exception:
        pass

# 可用的中文音色列表
VOICE_OPTIONS = {
    "xiaoxiao": {
        "id": "zh-CN-XiaoxiaoNeural",
        "name": "晓晓",
        "description": "女声 - 活泼可爱",
    },
    "yunxi": {
        "id": "zh-CN-YunxiNeural",
        "name": "云希",
        "description": "男声 - 成熟稳重",
    },
    "yunyang": {
        "id": "zh-CN-YunyangNeural",
        "name": "云扬",
        "description": "男声 - 新闻播报",
    },
    "xiaoyi": {
        "id": "zh-CN-XiaoyiNeural",
        "name": "晓伊",
        "description": "女声 - 温柔知性",
    },
    "yunxia": {
        "id": "zh-CN-YunxiaNeural",
        "name": "云霞",
        "description": "女声 - 活泼开朗",
    },
    "yunjian": {
        "id": "zh-CN-YunjianNeural",
        "name": "云健",
        "description": "男声 - 运动解说",
    },
    "cat": {
        "id": "zh-CN-XiaoxiaoNeural",
        "name": "喵喵",
        "description": "萌系 - 变声处理",
        "rate": "+10%",
        "pitch": "+25Hz",
    },
}

# 默认音色
DEFAULT_VOICE = "cat"


def get_voice_list() -> dict:
    """获取可用音色列表"""
    return VOICE_OPTIONS


def get_voice_id(voice_key: str) -> str:
    """根据音色键获取音色ID"""
    voice = VOICE_OPTIONS.get(voice_key, VOICE_OPTIONS[DEFAULT_VOICE])
    return voice["id"]


async def process_voice_message(bot: Bot, message: types.Message, user_id: int) -> str:
    """处理语音消息，转换为文字"""
    # 获取语音消息文件 ID
    file_id = message.voice.file_id
    file_info = await bot.get_file(file_id)
    
    # 确保 voice 目录存在
    voice_dir = Path(__file__).parent.parent / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    
    ogg_path = voice_dir / f"voice_{user_id}.ogg"
    mp3_path = voice_dir / f"voice_{user_id}.mp3"

    # 下载文件
    await bot.download_file(file_info.file_path, ogg_path)

    # 在单独线程中转换音频
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        await loop.run_in_executor(
            pool,
            lambda: AudioSegment.from_ogg(ogg_path).export(mp3_path, format="mp3"),
        )

    # 使用 OpenAI Whisper API 进行语音转文字
    if openai_client is None:
        raise ValueError("需要配置 OPENAI_API_KEY 才能使用语音转文字功能")
    
    with open(mp3_path, "rb") as audio_file:
        transcription = await asyncio.to_thread(
            lambda: openai_client.audio.transcriptions.create(
                model="whisper-1", file=audio_file
            )
        )
        return transcription.text


async def text_to_speech(bot: Bot, chat_id: int, text_message: str, voice_key: str = None) -> types.Message:
    """使用 edge-tts 从文本生成语音消息"""
    try:
        # 确保 voice 目录存在
        voice_dir = Path(__file__).parent.parent / "voice"
        voice_dir.mkdir(parents=True, exist_ok=True)
        
        speech_file_path = voice_dir / f"speech_{chat_id}.mp3"
        
        # 获取音色
        # 获取音色和参数
        if voice_key is None:
            voice_key = DEFAULT_VOICE
        
        voice_info = VOICE_OPTIONS.get(voice_key, VOICE_OPTIONS[DEFAULT_VOICE])
        voice_id = voice_info["id"]
        voice_rate = voice_info.get("rate", "+0%")
        voice_pitch = voice_info.get("pitch", "+0Hz")
        
        # 使用 edge-tts 生成语音
        communicate = edge_tts.Communicate(text_message, voice_id, rate=voice_rate, pitch=voice_pitch)
        path_str = str(speech_file_path)
        await communicate.save(path_str)
        
        audio = FSInputFile(speech_file_path)

        # 发送语音消息
        message = await bot.send_voice(
            chat_id, audio
        )
        
        # 发送后删除临时文件
        try:
            if speech_file_path.exists():
                os.remove(speech_file_path)
        except Exception as e:
            logging.error(f"删除临时语音文件失败: {e}")
            
        return message
    except Exception as e:
        logging.exception(e)
        return None
