"""
缓存 bot.get_me()，避免每条消息都请求 Telegram API。
"""
from typing import Optional

from aiogram.types import User

_bot_info: Optional[User] = None


async def get_bot_info(bot) -> User:
    global _bot_info
    if _bot_info is None:
        _bot_info = await bot.get_me()
    return _bot_info


async def warm_bot_cache(bot) -> None:
    await get_bot_info(bot)
