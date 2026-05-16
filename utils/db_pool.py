"""
数据库连接池和批量写入模块
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict

import aiosqlite
from aiosqlite import Connection

from utils.cache import LRUCache

# 数据库文件路径
DATA_DIR = Path(__file__).parent.parent / "data"
DB_FILE = DATA_DIR / "users_data.db"
GROUP_ADMIN_DB_FILE = DATA_DIR / "group_admin.db"

# 连接池配置
MAX_POOL_SIZE = 5
POOL_TIMEOUT = 30

# 批量写入配置
BATCH_SIZE = 10
BATCH_TIMEOUT = 2  # 秒

# 缓存配置
CACHE_SIZE = 1000
CACHE_TTL = 300  # 5分钟


class DatabasePool:
    """数据库连接池"""
    
    def __init__(self, db_file: Path, max_size: int = MAX_POOL_SIZE):
        self.db_file = db_file
        self.max_size = max_size
        self.pool: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._initialized = False
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """初始化连接池"""
        async with self._lock:
            if self._initialized:
                return
            
            # 确保数据目录存在
            self.db_file.parent.mkdir(parents=True, exist_ok=True)
            
            for _ in range(self.max_size):
                conn = await aiosqlite.connect(self.db_file)
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await self.pool.put(conn)
            
            self._initialized = True
    
    async def acquire(self) -> Connection:
        """获取连接"""
        if not self._initialized:
            await self.initialize()
        
        try:
            conn = await asyncio.wait_for(
                self.pool.get(),
                timeout=POOL_TIMEOUT
            )
            return conn
        except asyncio.TimeoutError:
            # 如果超时，创建新连接
            conn = await aiosqlite.connect(self.db_file)
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            return conn
    
    async def release(self, conn: Connection) -> None:
        """释放连接回池"""
        try:
            # 尝试放回池中
            self.pool.put_nowait(conn)
        except asyncio.QueueFull:
            # 池已满，关闭连接
            await conn.close()
    
    async def close_all(self) -> None:
        """关闭所有连接"""
        while not self.pool.empty():
            conn = await self.pool.get()
            await conn.close()


class BatchWriter:
    """批量写入器"""
    
    def __init__(self, batch_size: int = BATCH_SIZE, timeout: float = BATCH_TIMEOUT):
        self.batch_size = batch_size
        self.timeout = timeout
        self.pending_writes: Dict = {}
        self._flush_task = None
        self._lock = asyncio.Lock()
    
    async def write(self, user_id: int, data: dict) -> None:
        """添加写入任务"""
        async with self._lock:
            self.pending_writes[user_id] = data
            
            # 如果达到批量大小，立即刷新
            if len(self.pending_writes) >= self.batch_size:
                await self._flush()
            elif self._flush_task is None:
                # 启动延迟刷新任务
                self._flush_task = asyncio.create_task(self._delayed_flush())
    
    async def _delayed_flush(self) -> None:
        """延迟刷新"""
        await asyncio.sleep(self.timeout)
        async with self._lock:
            await self._flush()
    
    async def _flush(self) -> None:
        """刷新所有待写入的数据"""
        if not self.pending_writes:
            return
        
        writes_to_process = self.pending_writes.copy()
        self.pending_writes.clear()
        
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        
        # 确保数据目录存在
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # 批量写入数据库
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            
            for user_id, data in writes_to_process.items():
                try:
                    await conn.execute(
                        """
                        INSERT INTO UsersData (user_id, model, model_message_info, model_message_chat, messages, 
                        count_messages, max_out, voice_answer, system_message, pic_grade, pic_size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id) 
                        DO UPDATE SET
                            model = excluded.model,
                            model_message_info = excluded.model_message_info,
                            model_message_chat = excluded.model_message_chat,
                            messages = excluded.messages,
                            count_messages = excluded.count_messages,
                            max_out = excluded.max_out,
                            voice_answer = excluded.voice_answer,
                            system_message = excluded.system_message,
                            pic_grade = excluded.pic_grade,
                            pic_size = excluded.pic_size
                        """,
                        (
                            user_id,
                            data['model'],
                            data['model_message_info'],
                            data['model_message_chat'],
                            json.dumps(data['messages']),
                            data['count_messages'],
                            data['max_out'],
                            data['voice_answer'],
                            data['system_message'],
                            data['pic_grade'],
                            data['pic_size'],
                        ),
                    )
                except Exception as e:
                    logging.error(f"批量写入用户 {user_id} 数据失败: {e}")
            
            await conn.commit()
    
    async def flush(self) -> None:
        """立即刷新所有待写入数据"""
        async with self._lock:
            await self._flush()


# 全局实例
user_db_pool = DatabasePool(DB_FILE)
group_admin_db_pool = DatabasePool(GROUP_ADMIN_DB_FILE)
batch_writer = BatchWriter()
user_cache = LRUCache(max_size=CACHE_SIZE, ttl=CACHE_TTL)
