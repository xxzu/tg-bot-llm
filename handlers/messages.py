"""
消息处理器模块
处理文本、图片、语音消息
"""
import asyncio
import logging
import re

from aiogram import Router, F, types
from aiogram.enums import MessageEntityType, ParseMode
from aiogram.filters.state import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config.settings import OWNER_ID, bot
from config.text import pick_thinking_status
from models.database import get_or_create_user_data, save_user_data
from services.gemini import download_and_encode_image, process_image_with_gemini
from services.llm import get_invoker
from services.llm.types import LLMChatRequest, LLMVisionRequest
from utils.bot_cache import get_bot_info
from utils.stream_reply import stream_to_telegram_message_or_fallback
from utils.telegram_text import ensure_telegram_text, prepare_telegram_body
from services.voice import process_voice_message, text_to_speech
from utils.markdown import clean_text_for_tts
from utils.reply_context import merge_prompt_with_reply_context
from handlers.callbacks import ChangeValueState

# 导入群组管理模块
from services.group_admin import group_admin
from services.group_context import build_group_system_addon
from services.moderation_tools import ModerationToolContext, should_use_group_tools
from services.moderation_actions import apply_moderation_actions, parse_and_strip_mod_tags

router = Router()


def _message_mentions_bot(message: Message, bot_id: int, bot_username: str) -> bool:
    """检测 @用户名 或 选人提及（text_mention）是否指向本机器人。"""
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
    """从正文中去掉指向本机器人的 @ 或选人提及片段，得到用户实际问题。"""
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


@router.message(StateFilter(ChangeValueState.waiting_for_new_value))
async def process_new_value(message: types.Message, state: FSMContext):
    """处理新系统角色值输入"""
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

    user_data = await get_or_create_user_data(user_id, chat_id)
    user_data.system_message = sys_massage
    await save_user_data(user_id, chat_id)

    await state.clear()

    await message.answer(
        f"<b>系统角色已更改为：</b> <i>{user_data.system_message}</i>"
    )


@router.message(F.content_type.in_({"text", "voice"}))
async def chatgpt_text_handler(message: Message):
    """处理文本和语音消息"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type
    bot_me = await get_bot_info(bot)
    bot_id = bot_me.id
    bot_username = bot_me.username or ""

    # 在群组中先检查违规内容
    if chat_type in ["group", "supergroup"]:
        if not group_admin.async_init_done:
            await group_admin.init_db()
        
        # 检查用户是否被忽略
        if group_admin.is_ignored(chat_id, user_id):
            return  # 静默忽略该用户的消息
        
        if await group_admin.check_and_handle_message(bot, message):
            return

    # 处理群组消息的唤醒词 / @ / 回复机器人
    message_text = (message.text or "").strip()
    should_process = True

    if chat_type in ["group", "supergroup"]:
        should_process = False
        reply = message.reply_to_message
        reply_to_bot = bool(
            reply and reply.from_user and reply.from_user.id == bot_id
        )
        mentioned = _message_mentions_bot(message, bot_id, bot_username)
        wake = ("喵" in message_text) or ("晚安" in message_text)

        if reply_to_bot:
            should_process = True
        elif mentioned:
            message_text = _strip_bot_mention_from_text(message, bot_id, bot_username)
            if message_text or message.voice:
                should_process = True
        elif wake:
            should_process = True

    if not should_process:
        return
    
    # 权限检查
    if chat_type == "private" and user_id not in OWNER_ID:
        await message.answer("抱歉，您没有访问此机器人的权限。")
        return

    if chat_type in ["group", "supergroup"]:
        user_data, group_data = await asyncio.gather(
            get_or_create_user_data(user_id, chat_id),
            get_or_create_user_data(chat_id, chat_id),
        )
        current_model = group_data.model
        current_model_info = group_data.model_message_info
        current_system_message = group_data.system_message
    else:
        user_data = await get_or_create_user_data(user_id, chat_id)
        current_model = user_data.model
        current_model_info = user_data.model_message_info
        current_system_message = user_data.system_message

    await message.bot.send_chat_action(chat_id, action="typing")

    promt = ""

    if message.voice:
        promt = await process_voice_message(bot, message, user_id)
    elif message.text:
        promt = message_text
    else:
        promt = ""

    # 引用回复：喵喵 / @ / 回复机器人 触发时，把被引用消息正文并入上下文
    promt = merge_prompt_with_reply_context(promt, message.reply_to_message)

    invoker = get_invoker()
    model_spec = invoker.resolve(current_model)
    if not model_spec:
        await message.reply(
            f"当前模型未在配置中注册（{current_model}）。请在菜单中重新选择模型。"
        )
        return

    use_group_tools = should_use_group_tools(chat_type, model_spec)
    llm_request = LLMChatRequest(
        model_id=current_model,
        user_data=user_data,
        prompt=promt,
        system_instruction="",
    )

    user_data.messages.append({"role": "user", "content": promt})
    reply_already_sent = False
    response_message = ""
    status_message = None

    try:
        system_instruction = current_system_message if current_system_message else (
            "你叫喵喵，群聊风格：直接、机灵、略毒舌，能吐槽，但别刻薄过头。"
            "只答当前问题，不延伸；先说结论，再补一句；"
            "全文尽量1到3句。默认简体中文，不复述，不反问，不说废话，不要客服腔。"
            "评价类必须明确站队；不确定就直说，别瞎编。"
        )
        llm_request.system_instruction = system_instruction

        if chat_type in ["group", "supergroup"]:
            group_addon = await build_group_system_addon(
                bot, message, use_tools=use_group_tools
            )
            if group_addon:
                llm_request.system_instruction = f"{system_instruction}\n\n{group_addon}"

        if not invoker.is_available(current_model):
            await message.reply(invoker.unavailable_reason(current_model))
            return

        # 仅「用户发语音 + 开启语音回复」时走 TTS，且不用流式（避免先出字再录音）
        prefer_voice_out = bool(message.voice) and user_data.voice_answer

        if use_group_tools:
            status_message = await message.reply(pick_thinking_status())
            tool_ctx = await ModerationToolContext.from_message(message)
            response_message = await invoker.chat_with_tools(llm_request, tool_ctx)
        elif model_spec.supports("stream") and not prefer_voice_out:
            stream = invoker.iter_chat(llm_request)
            response_message = await stream_to_telegram_message_or_fallback(
                message, stream
            )
            reply_already_sent = True
        else:
            status_message = await message.reply(pick_thinking_status())
            response_message = await invoker.chat(llm_request)

        if not use_group_tools:
            response_message, mod_actions = parse_and_strip_mod_tags(
                response_message or ""
            )
            if chat_type in ["group", "supergroup"] and mod_actions:
                requester_is_admin = await group_admin.is_admin(
                    bot, chat_id, user_id
                )
                mod_notes = await apply_moderation_actions(
                    bot,
                    message,
                    mod_actions,
                    requester_is_admin=requester_is_admin,
                )
                if mod_notes:
                    note = "；".join(mod_notes)
                    if reply_already_sent:
                        await message.reply(f"🛡️ {note}")
                    if response_message:
                        response_message = f"{response_message}\n（{note}）"
                    else:
                        response_message = note

        response_message = ensure_telegram_text(response_message or "")

        user_data.messages.append({"role": "assistant", "content": response_message})
        user_data.count_messages += 1

        asyncio.create_task(save_user_data(user_id, chat_id))

        async def deliver_text_reply(response_text: str) -> None:
            """优先把占位「解毛线球」消息编辑成正式回复。"""
            response_text = ensure_telegram_text(response_text)
            if status_message and len(response_text) <= 4096:
                body, parse_mode = prepare_telegram_body(response_text)
                try:
                    if parse_mode == "HTML":
                        await status_message.edit_text(
                            body,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
                    else:
                        await status_message.edit_text(
                            body,
                            disable_web_page_preview=True,
                        )
                    return
                except Exception:
                    try:
                        await status_message.delete()
                    except Exception:
                        pass
            elif status_message:
                try:
                    await status_message.delete()
                except Exception:
                    pass
            if len(response_text) > 4096:
                await send_message_kwargs_long(response_text)
            else:
                await send_message_kwargs(response_text)

        async def send_message_kwargs(response_message_kwargs):
            body, parse_mode = prepare_telegram_body(response_message_kwargs)
            if parse_mode == "HTML":
                await message.reply(
                    body,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            else:
                await message.reply(body, disable_web_page_preview=True)

        async def send_message_kwargs_long(response_message_kwargs):
            content = ensure_telegram_text(response_message_kwargs)
            messages_split = content.split("\n")
            chunk = ""
            chunks = []

            for line in messages_split:
                if len(chunk) + len(line) + 1 > 4096:
                    chunks.append(chunk)
                    chunk = line
                else:
                    if chunk:
                        chunk += line + "\n"
                    else:
                        chunk = line

            if chunk:
                chunks.append(chunk)

            for i, chunk in enumerate(chunks):
                body, parse_mode = prepare_telegram_body(chunk)
                if i == 0:
                    if parse_mode == "HTML":
                        await message.reply(
                            body,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
                    else:
                        await message.reply(body, disable_web_page_preview=True)
                else:
                    if parse_mode == "HTML":
                        await message.answer(
                            body,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
                    else:
                        await message.answer(body, disable_web_page_preview=True)

        try:
            if prefer_voice_out and response_message.strip():
                await message.bot.send_chat_action(chat_id, action="record_voice")
                tts_text = clean_text_for_tts(response_message)
                voice_sent = await text_to_speech(
                    bot, message.chat.id, tts_text, user_data.voice_type
                )
                if voice_sent:
                    if status_message:
                        try:
                            await status_message.delete()
                        except Exception:
                            pass
                    return
                logging.warning("语音发送失败，降级为文字回复")

            if not reply_already_sent:
                await deliver_text_reply(response_message)

        except Exception as e:
            logging.exception(e)
            if not reply_already_sent:
                await deliver_text_reply(response_message)

    except Exception as e:
        logging.exception(e)
        if status_message:
            try:
                await status_message.delete()
            except Exception:
                pass
        await message.reply(f"发生错误：{e}")


@router.message(F.photo)
async def chatgpt_photo_vision_handler(message: Message, state: FSMContext):
    """处理图片消息"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type

    # 在群组中先检查违规内容
    if chat_type in ["group", "supergroup"]:
        if not group_admin.async_init_done:
            await group_admin.init_db()
        
        # 检查用户是否被忽略
        if group_admin.is_ignored(chat_id, user_id):
            return  # 静默忽略该用户的消息
        
        should_check = await group_admin.should_check_image(bot, chat_id, user_id)
        
        if should_check:
            if await group_admin.check_and_handle_message(bot, message):
                await group_admin.record_image_sent(chat_id, user_id)
                return
            await group_admin.record_image_sent(chat_id, user_id)
        else:
            return

    if chat_type == "private" and user_id not in OWNER_ID:
        await message.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    try:
        user_data = await get_or_create_user_data(user_id, chat_id)
        temp_message = await message.answer(pick_thinking_status())

        text = message.caption or "图片上有什么？"
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"

        base64_image = await download_and_encode_image(file_url)
        
        invoker = get_invoker()
        spec = invoker.resolve(user_data.model)
        vision_request = LLMVisionRequest(
            model_id=user_data.model,
            prompt=text,
            image_base64=base64_image,
        )
        if spec and spec.supports("vision") and invoker.is_available(user_data.model):
            ai_response = await invoker.vision(vision_request)
        else:
            ai_response = await process_image_with_gemini(text, base64_image)

        user_data.count_messages += 1
        await save_user_data(user_id, chat_id)
        
        await message.bot.delete_message(chat_id, temp_message.message_id)
        body, parse_mode = prepare_telegram_body(ai_response)
        if parse_mode == "HTML":
            await message.answer(body, parse_mode=ParseMode.HTML)
        else:
            await message.answer(body)

    except Exception as e:
        logging.exception(e)
        await message.reply(f"发生错误：{e}")
