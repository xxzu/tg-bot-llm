"""
用户数据模型模块
"""
import json
from pathlib import Path
from typing import Optional

import aiosqlite
from aiosqlite import Row
from peewee import Model, CharField, TextField, IntegerField, BooleanField

# 数据库文件路径
DATA_DIR = Path(__file__).parent.parent / "data"
DB_FILE = DATA_DIR / "users_data.db"


class BaseModel(Model):
    class Meta:
        database = DB_FILE


class UsersData(BaseModel):
    """用户数据 Peewee 模型"""
    user_id = CharField(primary_key=True)
    model = CharField()
    model_message_info = CharField()
    model_message_chat = CharField()
    messages = TextField()
    count_messages = IntegerField()
    max_out = IntegerField()
    voice_answer = BooleanField()
    system_message = TextField()
    pic_grade = CharField()
    pic_size = CharField()


class UserData:
    """用户数据类"""
    
    def __init__(self, user_id, chat_id=None):
        self.user_id = user_id
        self.chat_id = chat_id if chat_id is not None else user_id
        self.messages = []
        self._count_messages = 0
        from services.llm.registry import default_model_for_session

        model_id, model_info, max_out = default_model_for_session()
        self._model = model_id
        self._model_message_info = model_info
        self._model_message_chat = ""
        self._max_out = max_out
        self._voice_answer = False
        self._voice_type = "cat"  # 默认音色
        self._system_message = ""
        self._pic_grade = "standard"
        self._pic_size = "1024x1024"

    def __str__(self):
        return (
            f"user_id: {self.user_id}\n"
            f"messages: {self.messages}\n"
            f"count_messages: {self._count_messages}\n"
            f"model: {self._model}\n"
            f"model_message_info: {self._model_message_info}\n"
            f"model_message_chat: {self._model_message_chat[:-2] if self._model_message_chat else ''}\n"
            f"max_out: {self._max_out}\n"
            f"voice_answer: {self._voice_answer}\n"
            f"voice_type: {self._voice_type}\n"
            f"system_message: {self._system_message}\n"
            f"pic_grade: {self._pic_grade}\n"
            f"pic_size: {self._pic_size}"
        )

    @staticmethod
    async def load_from_db(user_id, chat_id=None, db_pool=None) -> Optional["UserData"]:
        """从数据库加载用户数据"""
        if chat_id is None:
            chat_id = user_id
        
        chat_key = f"{user_id}_{chat_id}"
        
        # 确保数据目录存在
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = Row
            async with conn.execute(
                "SELECT * FROM UsersData WHERE user_id = ?", (chat_key,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    user_data = UserData(user_id, chat_id)
                    user_data._model = row["model"]
                    user_data._model_message_info = row["model_message_info"]
                    user_data._model_message_chat = row["model_message_chat"]
                    user_data.messages = (
                        json.loads(row["messages"]) if row["messages"] else []
                    )
                    user_data._count_messages = row["count_messages"]
                    user_data._max_out = row["max_out"]
                    user_data._voice_answer = row["voice_answer"]
                    user_data._voice_type = row["voice_type"] if "voice_type" in row.keys() else "cat"
                    user_data._system_message = row["system_message"]
                    user_data._pic_grade = row["pic_grade"]
                    user_data._pic_size = row["pic_size"]
                    return user_data
                return None

    async def save_to_db(self, db_pool=None) -> None:
        """保存用户数据到数据库"""
        chat_key = f"{self.user_id}_{self.chat_id}"
        
        # 确保数据目录存在
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute(
                """
                INSERT INTO UsersData (user_id, model, model_message_info, model_message_chat, messages, 
                count_messages, max_out, voice_answer, voice_type, system_message, pic_grade, pic_size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) 
                DO UPDATE SET
                    model = excluded.model,
                    model_message_info = excluded.model_message_info,
                    model_message_chat = excluded.model_message_chat,
                    messages = excluded.messages,
                    count_messages = excluded.count_messages,
                    max_out = excluded.max_out,
                    voice_answer = excluded.voice_answer,
                    voice_type = excluded.voice_type,
                    system_message = excluded.system_message,
                    pic_grade = excluded.pic_grade,
                    pic_size = excluded.pic_size
                """,
                (
                    chat_key,
                    self._model,
                    self._model_message_info,
                    self._model_message_chat,
                    json.dumps(self.messages),
                    self._count_messages,
                    self._max_out,
                    self._voice_answer,
                    self._voice_type,
                    self._system_message,
                    self._pic_grade,
                    self._pic_size,
                ),
            )
            await conn.commit()

    @property
    def pic_grade(self):
        return self._pic_grade

    @pic_grade.setter
    def pic_grade(self, value):
        self._pic_grade = value

    @property
    def pic_size(self):
        return self._pic_size

    @pic_size.setter
    def pic_size(self, value):
        self._pic_size = value

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, value):
        self._model = value

    @property
    def count_messages(self):
        return self._count_messages

    @count_messages.setter
    def count_messages(self, value):
        self._count_messages = value

    @property
    def model_message_info(self):
        return self._model_message_info

    @model_message_info.setter
    def model_message_info(self, value):
        self._model_message_info = value

    @property
    def model_message_chat(self):
        return self._model_message_chat

    @model_message_chat.setter
    def model_message_chat(self, value):
        self._model_message_chat = value

    @property
    def max_out(self):
        return self._max_out

    @max_out.setter
    def max_out(self, value):
        self._max_out = value

    @property
    def voice_answer(self):
        return self._voice_answer

    @voice_answer.setter
    def voice_answer(self, value):
        self._voice_answer = value

    @property
    def voice_type(self):
        return self._voice_type

    @voice_type.setter
    def voice_type(self, value):
        self._voice_type = value

    @property
    def system_message(self):
        return self._system_message

    @system_message.setter
    def system_message(self, value):
        self._system_message = value

