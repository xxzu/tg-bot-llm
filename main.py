"""
Gemini Telegram Bot 主入口文件
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import bot
from handlers import router
from models.database import init_db
from services.http_session import close_http_session
from utils.bot_cache import warm_bot_cache
from utils.db_pool import batch_writer

# 导入群组管理模块
from services.group_admin import group_admin


async def start_bot():
    """初始化并启动 Bot"""
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    return dp


async def main():
    """主函数"""
    try:
        # 初始化用户数据库表
        await init_db()
        
        # 初始化群组管理数据库
        await group_admin.init_db()

        await warm_bot_cache(bot)

        dp = await start_bot()
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logging.exception(f"An error occurred: {e}")
    finally:
        # 关闭前刷新所有待写入数据
        await batch_writer.flush()
        await close_http_session()
        await bot.session.close()


def _setup_logging() -> None:
    _level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, _level, logging.INFO)
    fmt = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setFormatter(fmt)
    root.addHandler(stream_h)
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_h = logging.FileHandler(log_dir / "bot.log", encoding="utf-8")
    file_h.setFormatter(fmt)
    root.addHandler(file_h)


if __name__ == "__main__":
    _setup_logging()
    asyncio.run(main())
