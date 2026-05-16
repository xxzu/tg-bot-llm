"""
数据库操作模块
"""
from pathlib import Path
from typing import List

import aiosqlite

from models.user import UserData
from utils.db_pool import batch_writer, user_cache

# 数据库文件路径
DATA_DIR = Path(__file__).parent.parent / "data"
DB_FILE = DATA_DIR / "users_data.db"

# 用于存储用户数据的字典（内存缓存）
users_data = {}


async def init_db() -> None:
    """初始化数据库"""
    # 确保数据目录存在
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS UsersData (
                user_id TEXT PRIMARY KEY,
                model TEXT,
                model_message_info TEXT,
                model_message_chat TEXT,
                messages TEXT,
                count_messages INTEGER,
                max_out INTEGER,
                voice_answer BOOLEAN,
                voice_type TEXT DEFAULT 'cat',
                system_message TEXT,
                pic_grade TEXT,
                pic_size TEXT
            )
            """
        )
        
        # 添加 voice_type 列（如果不存在）
        try:
            await conn.execute("ALTER TABLE UsersData ADD COLUMN voice_type TEXT DEFAULT 'cat'")
        except Exception:
            pass  # 列已存在
        
        await conn.commit()


async def get_or_create_user_data(user_id: int, chat_id: int = None) -> UserData:
    """获取或创建用户数据（区分私聊和群组，带缓存）"""
    if chat_id is None:
        chat_id = user_id
    
    cache_key = f"{user_id}_{chat_id}"
    
    # 先检查内存缓存
    if cache_key in users_data:
        return users_data[cache_key]
    
    # 检查 LRU 缓存
    cached_data = user_cache.get(cache_key)
    if cached_data:
        user_data = UserData(user_id, chat_id)
        user_data._model = cached_data['model']
        user_data._model_message_info = cached_data['model_message_info']
        user_data._model_message_chat = cached_data['model_message_chat']
        user_data.messages = cached_data['messages']
        user_data._count_messages = cached_data['count_messages']
        user_data._max_out = cached_data['max_out']
        user_data._voice_answer = cached_data['voice_answer']
        user_data._voice_type = cached_data.get('voice_type', 'cat')
        user_data._system_message = cached_data['system_message']
        user_data._pic_grade = cached_data['pic_grade']
        user_data._pic_size = cached_data['pic_size']
        users_data[cache_key] = user_data
        return user_data

    # 从数据库加载
    user_data = await UserData.load_from_db(user_id, chat_id)
    if user_data is None:
        user_data = UserData(user_id, chat_id)

    users_data[cache_key] = user_data
    return user_data


async def save_user_data(user_id: int, chat_id: int = None, immediate: bool = False) -> None:
    """保存用户数据（区分私聊和群组，使用批量写入和缓存）"""
    if chat_id is None:
        chat_id = user_id
    
    cache_key = f"{user_id}_{chat_id}"
    
    user_data = users_data.get(cache_key)
    if not user_data:
        return
    
    # 更新缓存
    cache_data = {
        'model': user_data._model,
        'model_message_info': user_data._model_message_info,
        'model_message_chat': user_data._model_message_chat,
        'messages': user_data.messages,
        'count_messages': user_data._count_messages,
        'max_out': user_data._max_out,
        'voice_answer': user_data._voice_answer,
        'voice_type': user_data._voice_type,
        'system_message': user_data._system_message,
        'pic_grade': user_data._pic_grade,
        'pic_size': user_data._pic_size,
    }
    user_cache.set(cache_key, cache_data)
    
    # 批量写入或立即写入
    if immediate:
        await user_data.save_to_db()
    else:
        await batch_writer.write(cache_key, cache_data)


async def get_all_users() -> List[str]:
    """获取所有用户ID"""
    # 确保数据目录存在
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT user_id FROM UsersData") as cursor:
            return [str(row["user_id"]) for row in await cursor.fetchall()]
