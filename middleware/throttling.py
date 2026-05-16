"""
限流中间件模块
"""
import time
from collections import defaultdict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    """消息限流中间件"""
    
    def __init__(self, spin: float = 1.0):
        self.spin = spin
        self.last_time = defaultdict(float)

    async def __call__(
        self,
        handler,
        event: TelegramObject,
        data: dict,
    ):
        user_id = event.from_user.id if hasattr(event, "from_user") else None
        if user_id:
            current_time = time.time()
            if current_time - self.last_time[user_id] < self.spin:
                return
            self.last_time[user_id] = current_time
        return await handler(event, data)
