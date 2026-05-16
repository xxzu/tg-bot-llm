"""
配置管理模块
集中管理所有配置项
"""
import os
from datetime import datetime
from pathlib import Path

import pytz
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 设置时区
timezone = pytz.timezone("Asia/Shanghai")

# 获取当前日期和时间
current_datetime = datetime.now(timezone)
formatted_datetime = current_datetime.strftime("%Y-%m-%d %H:%M:%S")

# 从环境变量读取配置
TOKEN = os.getenv("TG_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# 从环境变量读取所有者ID列表
owner_id_str = os.getenv("OWNER_ID", "")
OWNER_ID = {int(owner_id.strip()) for owner_id in owner_id_str.split(",") if owner_id.strip()}

# 数据库文件路径
DATA_DIR = Path(__file__).parent.parent / "data"
DB_FILE = DATA_DIR / "users_data.db"
GROUP_ADMIN_DB_FILE = DATA_DIR / "group_admin.db"

# 创建 Bot 实例
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
