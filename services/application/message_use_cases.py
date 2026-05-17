"""文本/图片消息应用用例。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from aiogram import Bot
from aiogram.types import Message

from config.text import pick_thinking_status
from models.database import get_or_create_user_data, save_user_data
from services.application.dto import (
    ChatSessionContext,
    IncomingChatContext,
    PhotoHandleResult,
    ReplyDeliveryMode,
    TextHandleResult,
)
from services.application.trigger_policy import evaluate_group_trigger
from services.gemini import download_and_encode_image, process_image_with_gemini
from services.group_context import build_group_system_addon
from services.llm import get_invoker
from services.llm.registry import resolve_vision_model_id
from services.llm.conversation import ConversationSnapshot
from services.llm.types import LLMChatRequest, LLMVisionRequest
from services.moderation_actions import apply_moderation_actions, parse_and_strip_mod_tags
from services.moderation_tools import should_use_group_tools
from services.ports.moderation_mapping import build_tool_context_from_message
from utils.reply_context import merge_prompt_with_reply_context
from utils.stream_reply import stream_to_telegram_message_or_fallback
from utils.telegram_text import ensure_telegram_text

DEFAULT_SYSTEM = (
    "你叫喵喵，群聊风格：直接、机灵、略毒舌，能吐槽，但别刻薄过头。"
    "只答当前问题，不延伸；先说结论，再补一句；"
    "全文尽量1到3句。默认简体中文，不复述，不反问，不说废话，不要客服腔。"
    "评价类必须明确站队；不确定就直说，别瞎编。"
)


class HandleTextMessageUseCase:
    async def execute(
        self,
        *,
        bot: Bot,
        message: Message,
        incoming: IncomingChatContext,
        user_data: Any,
        group_data: Optional[Any],
        status_message_holder: dict,
    ) -> TextHandleResult:
        """
        status_message_holder: 可变 dict，键 'msg' 由 handler 写入占位 Message（供 presenter 编辑）。
        """
        chat_type = incoming.chat_type
        user_id = incoming.user_id
        chat_id = incoming.chat_id

        if not evaluate_group_trigger(incoming):
            return TextHandleResult(handled=False)

        if chat_type in ("group", "supergroup") and group_data is not None:
            model_source = group_data
        else:
            model_source = user_data
        session = ChatSessionContext.from_user_data(
            model_source, storage_user_id=user_id, storage_chat_id=chat_id
        )
        user_session = ChatSessionContext.from_user_data(
            user_data, storage_user_id=user_id, storage_chat_id=chat_id
        )

        promt = incoming.message_text
        if message.voice:
            from services.voice import process_voice_message

            promt = await process_voice_message(bot, message, user_id)
        promt = merge_prompt_with_reply_context(promt, message.reply_to_message)

        invoker = get_invoker()
        model_spec = invoker.resolve(session.model_id)
        if not model_spec:
            return TextHandleResult(
                early_reply=f"当前模型未在配置中注册（{session.model_id}）。请在菜单中重新选择模型。",
                persist_user_id=user_id,
                persist_chat_id=chat_id,
            )

        use_group_tools = should_use_group_tools(chat_type, model_spec)
        system_instruction = session.system_message or DEFAULT_SYSTEM
        conversation = ConversationSnapshot.from_session(user_session)

        llm_request = LLMChatRequest(
            model_id=session.model_id,
            conversation=conversation,
            prompt=promt,
            system_instruction=system_instruction,
        )

        if chat_type in ("group", "supergroup"):
            try:
                group_addon = await build_group_system_addon(
                    bot, message, use_tools=use_group_tools
                )
            except Exception as e:
                import logging

                logging.exception("构建群聊上下文失败，将跳过群管附加说明: %s", e)
                group_addon = ""
            if group_addon:
                llm_request.system_instruction = f"{system_instruction}\n\n{group_addon}"

        if not invoker.is_available(session.model_id):
            return TextHandleResult(
                early_reply=invoker.unavailable_reason(session.model_id),
                persist_user_id=user_id,
                persist_chat_id=chat_id,
            )

        prefer_voice_out = incoming.has_voice and user_session.voice_answer
        delivery_mode = ReplyDeliveryMode.NONE
        response_message = ""

        try:
            if use_group_tools:
                status_message_holder["msg"] = await message.reply(pick_thinking_status())
                tool_ctx = await build_tool_context_from_message(message)
                response_message = await invoker.chat_with_tools(llm_request, tool_ctx)
                delivery_mode = ReplyDeliveryMode.PLACEHOLDER_THEN_EDIT
            elif model_spec.supports("stream") and not prefer_voice_out:
                stream = invoker.iter_chat(llm_request)
                response_message = await stream_to_telegram_message_or_fallback(
                    message, stream
                )
                delivery_mode = ReplyDeliveryMode.STREAM_ALREADY_SENT
            else:
                status_message_holder["msg"] = await message.reply(pick_thinking_status())
                response_message = await invoker.chat(llm_request)
                delivery_mode = ReplyDeliveryMode.PLACEHOLDER_THEN_EDIT

            mod_note_reply = None
            if not use_group_tools:
                response_message, mod_actions = parse_and_strip_mod_tags(
                    response_message or ""
                )
                if chat_type in ("group", "supergroup") and mod_actions:
                    from services.group_admin import group_admin

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
                        if delivery_mode == ReplyDeliveryMode.STREAM_ALREADY_SENT:
                            mod_note_reply = note
                        elif response_message:
                            response_message = f"{response_message}\n（{note}）"
                        else:
                            response_message = note

            response_message = ensure_telegram_text(response_message or "")
            user_session.messages.append({"role": "user", "content": promt})
            user_session.messages.append(
                {"role": "assistant", "content": response_message}
            )
            user_session.count_messages += 1
            user_session.apply_to_user_data(user_data)
            asyncio.create_task(save_user_data(user_id, chat_id))

            return TextHandleResult(
                response_text=response_message,
                delivery_mode=delivery_mode,
                prefer_voice_out=prefer_voice_out,
                mod_note_reply=mod_note_reply,
                persist_user_id=user_id,
                persist_chat_id=chat_id,
            )
        except Exception as e:
            logging.exception(e)
            return TextHandleResult(
                error_message=str(e),
                delivery_mode=delivery_mode,
                persist_user_id=user_id,
                persist_chat_id=chat_id,
            )


class HandlePhotoMessageUseCase:
    async def execute(
        self,
        *,
        bot: Bot,
        message: Message,
        user_data: Any,
    ) -> PhotoHandleResult:
        user_id = message.from_user.id
        chat_id = message.chat.id

        text = message.caption or "请用中文简要描述这张图片的内容。"
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        base64_image = await download_and_encode_image(file_url)

        invoker = get_invoker()
        chat_model_id = user_data.model
        vision_model_id = resolve_vision_model_id(
            chat_model_id, purpose="describe"
        )
        if not vision_model_id:
            return PhotoHandleResult(
                early_reply=(
                    "当前没有可用的识图模型。请在 .env 配置 GEMINI_API_KEY 或 "
                    "OPENROUTER_API_KEY，或在菜单选择带「视觉」的 OpenRouter 模型。"
                ),
                persist_user_id=user_id,
                persist_chat_id=chat_id,
            )

        vision_request = LLMVisionRequest(
            model_id=vision_model_id,
            prompt=text,
            image_base64=base64_image,
        )
        try:
            ai_response = await invoker.vision(vision_request)
        except Exception as first_err:
            err_text = str(first_err).lower()
            if vision_model_id == chat_model_id and (
                "multimodal" in err_text or "not a multimodal" in err_text
            ):
                fallback_id = resolve_vision_model_id("", purpose="describe")
                if fallback_id and fallback_id != vision_model_id:
                    vision_request.model_id = fallback_id
                    ai_response = await invoker.vision(vision_request)
                else:
                    ai_response = await process_image_with_gemini(text, base64_image)
            else:
                raise first_err

        user_data.count_messages += 1
        await save_user_data(user_id, chat_id)

        return PhotoHandleResult(
            response_text=ai_response,
            persist_user_id=user_id,
            persist_chat_id=chat_id,
        )
