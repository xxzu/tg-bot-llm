"""
消息处理器：薄适配层，业务编排在 services.application。
"""
import asyncio
import re

from aiogram import Router, F, types
from aiogram.enums import MessageEntityType
from aiogram.filters.state import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config.settings import OWNER_ID, bot
from config.text import pick_thinking_status
from handlers.states import ChangeValueState
from models.database import (
    get_or_create_user_data,
    model_storage_ids,
    save_user_data,
)
from services.application.dto import IncomingChatContext, ReplyDeliveryMode
from services.application.message_use_cases import (
    HandlePhotoMessageUseCase,
    HandleTextMessageUseCase,
)
from services.application.response_presenter import ResponsePresenter
from services.group_admin import group_admin
from services.group_admin.image_moderation import moderate_group_photo
from services.voice import process_voice_message, text_to_speech
from utils.bot_cache import get_bot_info
from utils.markdown import clean_text_for_tts

router = Router()

_text_use_case = HandleTextMessageUseCase()
_photo_use_case = HandlePhotoMessageUseCase()


def _message_mentions_bot(message: Message, bot_id: int, bot_username: str) -> bool:
    if message.text and message.entities:
        for ent in message.entities:
            if ent.type == MessageEntityType.MENTION and bot_username:
                frag = message.text[ent.offset : ent.offset + ent.length]
                if frag.lower() == f"@{bot_username.lower()}":
                    return True
            if ent.type == MessageEntityType.TEXT_MENTION and ent.user and ent.user.id == bot_id:
                return True
    if bot_username and message.text and f"@{bot_username}".lower() in message.text.lower():
        return True
    return False


def _strip_bot_mention_from_text(message: Message, bot_id: int, bot_username: str) -> str:
    if not message.text:
        return ""
    text = message.text
    ranges = []
    if message.entities:
        for ent in message.entities:
            if ent.type == MessageEntityType.MENTION and bot_username:
                frag = text[ent.offset : ent.offset + ent.length]
                if frag.lower() == f"@{bot_username.lower()}":
                    ranges.append((ent.offset, ent.length))
            if ent.type == MessageEntityType.TEXT_MENTION and ent.user and ent.user.id == bot_id:
                ranges.append((ent.offset, ent.length))
    if ranges:
        ranges.sort(key=lambda x: x[0], reverse=True)
        for off, ln in ranges:
            text = text[:off] + " " + text[off + ln :]
        return re.sub(r"\s+", " ", text).strip()
    if bot_username:
        pat = re.compile(r"\s*@" + re.escape(bot_username) + r"\b", re.IGNORECASE)
        return pat.sub(" ", text).replace("  ", " ").strip()
    return text.strip()


_WAKE_WORDS = ("喵", "喵喵", "晚安")


def _message_has_wake_word(text: str) -> bool:
    if not text:
        return False
    return any(w in text for w in _WAKE_WORDS)


def _build_incoming(message: Message, bot_id: int, bot_username: str) -> IncomingChatContext:
    message_text = (message.text or "").strip()
    reply = message.reply_to_message
    reply_to_bot = bool(reply and reply.from_user and reply.from_user.id == bot_id)
    mentioned = _message_mentions_bot(message, bot_id, bot_username)
    if mentioned:
        message_text = _strip_bot_mention_from_text(message, bot_id, bot_username)
    return IncomingChatContext(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        chat_type=message.chat.type,
        message_text=message_text,
        has_voice=bool(message.voice),
        is_reply_to_bot=reply_to_bot,
        is_mention=mentioned,
        has_wake_word=_message_has_wake_word(message.text or ""),
    )


async def _ensure_group_gate(bot, message: Message) -> bool:
    """群聊违规预审；已处理返回 True。"""
    if message.chat.type not in ("group", "supergroup"):
        return False
    if not group_admin.async_init_done:
        await group_admin.init_db()
    if group_admin.is_ignored(message.chat.id, message.from_user.id):
        return True
    return await group_admin.check_and_handle_message(bot, message)


@router.message(StateFilter(ChangeValueState.waiting_for_new_value))
async def process_new_value(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if user_id not in OWNER_ID:
        await message.answer("抱歉，您没有访问此机器人的权限。")
        return
    sys_massage = ""
    if message.voice:
        sys_massage = await process_voice_message(bot, message, user_id)
    elif message.text:
        sys_massage = message.text
    storage_uid, storage_cid = model_storage_ids(
        user_id, chat_id, message.chat.type
    )
    settings = await get_or_create_user_data(storage_uid, storage_cid)
    settings.system_message = sys_massage
    await save_user_data(storage_uid, storage_cid)
    await state.clear()
    await message.answer(f"<b>系统角色已更改为：</b> <i>{settings.system_message}</i>")


@router.message(F.content_type.in_({"text", "voice"}))
async def chatgpt_text_handler(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type
    bot_me = await get_bot_info(bot)
    bot_id = bot_me.id
    bot_username = bot_me.username or ""

    if await _ensure_group_gate(bot, message):
        return

    incoming = _build_incoming(message, bot_id, bot_username)
    if chat_type in ("group", "supergroup") and not (
        incoming.is_reply_to_bot
        or (incoming.is_mention and (incoming.message_text or incoming.has_voice))
        or incoming.has_wake_word
    ):
        return

    if chat_type == "private" and user_id not in OWNER_ID:
        await message.answer("抱歉，您没有访问此机器人的权限。")
        return

    group_data = None
    if chat_type in ("group", "supergroup"):
        user_data, group_data = await asyncio.gather(
            get_or_create_user_data(user_id, chat_id),
            get_or_create_user_data(chat_id, chat_id),
        )
    else:
        user_data = await get_or_create_user_data(user_id, chat_id)

    presenter = ResponsePresenter(message, bot)
    await presenter.send_typing()

    status_holder: dict = {}
    result = await _text_use_case.execute(
        bot=bot,
        message=message,
        incoming=incoming,
        user_data=user_data,
        group_data=group_data,
        status_message_holder=status_holder,
    )

    if not result.handled:
        return
    if result.early_reply:
        await presenter.reply_plain(result.early_reply)
        return
    if result.error_message:
        await presenter.delete_status(status_holder.get("msg"))
        await presenter.reply_plain(f"发生错误：{result.error_message}")
        return

    status_message = status_holder.get("msg")
    try:
        if result.mod_note_reply:
            await presenter.send_mod_note(result.mod_note_reply)
        if result.prefer_voice_out and result.response_text.strip():
            await presenter.send_record_voice()
            voice_sent = await text_to_speech(
                bot,
                chat_id,
                clean_text_for_tts(result.response_text),
                user_data.voice_type,
            )
            if voice_sent:
                await presenter.delete_status(status_message)
                return
        await presenter.deliver_text(
            result.response_text,
            status_message=status_message,
            delivery_mode=result.delivery_mode,
        )
    except Exception as e:
        import logging

        logging.exception(e)
        if result.delivery_mode != ReplyDeliveryMode.STREAM_ALREADY_SENT:
            await presenter.deliver_text(
                result.response_text,
                status_message=status_message,
                delivery_mode=ReplyDeliveryMode.PLACEHOLDER_THEN_EDIT,
            )


@router.message(F.photo)
async def chatgpt_photo_vision_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type

    if chat_type in ("group", "supergroup"):
        if not group_admin.async_init_done:
            await group_admin.init_db()
        if group_admin.is_ignored(chat_id, user_id):
            return
        should_check = await group_admin.should_check_image(bot, chat_id, user_id)
        if not should_check:
            return
        if await group_admin.check_and_handle_message(bot, message):
            await group_admin.record_image_sent(chat_id, user_id)
            return
        mod_outcome = await moderate_group_photo(bot, message)
        await group_admin.record_image_sent(chat_id, user_id)
        if mod_outcome.brief_notice:
            await message.answer(mod_outcome.brief_notice)
        elif mod_outcome.error:
            import logging

            logging.warning("群聊图片审核: %s", mod_outcome.error)
        return

    if chat_type == "private" and user_id not in OWNER_ID:
        await message.answer("抱歉，您没有访问此机器人的权限。")
        return
    if state is not None:
        await state.clear()

    presenter = ResponsePresenter(message, bot)
    temp_message = await message.answer(pick_thinking_status())
    try:
        user_data = await get_or_create_user_data(user_id, chat_id)
        result = await _photo_use_case.execute(
            bot=bot, message=message, user_data=user_data
        )
        if result.early_reply:
            await presenter.reply_plain(result.early_reply)
            return
        await presenter.send_photo_answer(
            result.response_text, temp_message=temp_message
        )
    except Exception as e:
        import logging

        logging.exception(e)
        await presenter.reply_plain(f"发生错误：{e}")
