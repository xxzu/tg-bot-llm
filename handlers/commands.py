"""
命令处理器模块
处理 /start, /menu, /help 命令
"""
from aiogram import Router, F, flags
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config.settings import OWNER_ID
from config.buttons import keyboard
from config.text import start_message, help_message
from models.database import get_or_create_user_data, save_user_data

router = Router()


@router.message(F.text == "/start")
@flags.throttling_key("spin")
async def command_start_handler(message: Message, state: FSMContext):
    """处理 /start 命令"""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id not in OWNER_ID:
        await message.answer(
            f"<i>抱歉，您没有访问此机器人的权限。\n"
            f"您的用户 ID：</i> <b>{user_id}</b>"
        )
        return

    if state is not None:
        await state.clear()

    # 获取或创建用户数据对象
    user_data = await get_or_create_user_data(user_id, chat_id)

    user_data.model = "gemini-3-pro-preview"
    user_data.model_message_info = "Gemini 3 Pro"
    user_data.model_message_chat = ""
    user_data.messages = []
    user_data.count_messages = 0
    user_data.max_out = 128000
    user_data.voice_answer = False
    user_data.system_message = ""
    user_data.pic_grade = "standard"
    user_data.pic_size = "1024x1024"

    await save_user_data(user_id, chat_id)
    await message.answer(start_message)


@router.message(F.text == "/menu")
@flags.throttling_key("spin")
async def process_key_button(message: Message, state: FSMContext):
    """处理 /menu 命令"""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id not in OWNER_ID:
        await message.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    await get_or_create_user_data(user_id, chat_id)
    await message.answer(text="请选择操作：", reply_markup=keyboard)


@router.message(F.text == "/help")
@flags.throttling_key("spin")
async def help_handler(message: Message, state: FSMContext):
    """处理 /help 命令"""
    user_id = message.from_user.id

    if user_id not in OWNER_ID:
        await message.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    await get_or_create_user_data(user_id)
    await message.answer(help_message)
