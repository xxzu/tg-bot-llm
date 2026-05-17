"""
群管处置对象解析：访客机器人广告归责于真实用户（Telegram Bot API 10.0+）。

Message.guest_bot_caller_user — 触发访客机器人回复的真人用户。
同群同机器人若曾绑定过 caller，后续无 caller 字段的消息仍归责该用户。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from aiogram.types import Message, User

logger = logging.getLogger(__name__)


class GuestBotBindingPort(Protocol):
    async def bind_guest_bot_caller(
        self,
        chat_id: int,
        bot_user_id: int,
        caller_user_id: int,
        caller_username: str = "",
    ) -> None: ...

    async def lookup_guest_bot_caller(
        self, chat_id: int, bot_user_id: int
    ) -> Optional[tuple[int, str]]: ...


@dataclass(frozen=True)
class ModerationActor:
    """应对广告/违规时计次、警告、封禁的对象（真人）。"""

    user_id: int
    username: str
    mention: str
    display_name: str
    via_guest_bot: bool = False
    bot_sender_id: Optional[int] = None
    via_guest_binding: bool = False


def message_sender_snapshot(message: Message) -> Dict[str, Any]:
    """提取 Telegram 消息上与发送者/访客机器人相关的原始字段（便于对照日志）。"""
    from_user = message.from_user
    caller: Optional[User] = getattr(message, "guest_bot_caller_user", None)
    caller_chat = getattr(message, "guest_bot_caller_chat", None)
    via_bot: Optional[User] = getattr(message, "via_bot", None)
    return {
        "chat_id": message.chat.id,
        "msg_id": message.message_id,
        "from_user_id": from_user.id if from_user else None,
        "from_user_is_bot": from_user.is_bot if from_user else None,
        "from_user_username": from_user.username if from_user else None,
        "guest_bot_caller_user_id": caller.id if caller else None,
        "guest_bot_caller_username": caller.username if caller else None,
        "guest_bot_caller_is_bot": caller.is_bot if caller else None,
        "guest_bot_caller_chat_id": caller_chat.id if caller_chat else None,
        "guest_query_id": getattr(message, "guest_query_id", None),
        "via_bot_id": via_bot.id if via_bot else None,
        "sender_chat_id": message.sender_chat.id if message.sender_chat else None,
    }


def log_message_sender_context(message: Message, *, tag: str) -> Dict[str, Any]:
    """记录群消息发送者上下文（访客机器人归责调试）。"""
    snap = message_sender_snapshot(message)
    logger.info("群消息发送者上下文 tag=%s %s", tag, snap)
    return snap


def log_moderation_actor_resolution(
    message: Message,
    actor: Optional[ModerationActor],
    *,
    tag: str,
) -> None:
    """记录归责结果：最终处置对象 vs Telegram 原始字段。"""
    snap = message_sender_snapshot(message)
    if actor is None:
        logger.info(
            "群管归责 tag=%s result=无真人对象(仅可删机器人消息) snapshot=%s",
            tag,
            snap,
        )
        return
    logger.info(
        "群管归责 tag=%s result=user_id=%s via_guest_bot=%s via_binding=%s "
        "bot_sender_id=%s mention=%r display=%r snapshot=%s",
        tag,
        actor.user_id,
        actor.via_guest_bot,
        actor.via_guest_binding,
        actor.bot_sender_id,
        actor.mention,
        actor.display_name,
        snap,
    )


def _labels(user: User) -> tuple[str, str, str]:
    username = user.username or user.first_name or str(user.id)
    mention = (
        f"@{username}"
        if username and not str(username).isdigit()
        else (user.first_name or str(user.id))
    )
    display = " ".join(
        filter(None, [user.first_name, user.last_name, user.username])
    ) or str(user.id)
    return username, mention, display


def _actor_from_user_id(
    user_id: int,
    username: str,
    *,
    via_guest_bot: bool,
    bot_sender_id: Optional[int],
    via_guest_binding: bool,
) -> ModerationActor:
    mention = (
        f"@{username}"
        if username and not str(username).isdigit()
        else username
    )
    return ModerationActor(
        user_id=user_id,
        username=username,
        mention=mention,
        display_name=username,
        via_guest_bot=via_guest_bot,
        bot_sender_id=bot_sender_id,
        via_guest_binding=via_guest_binding,
    )


async def resolve_moderation_actor(
    message: Message,
    bindings: Optional[GuestBotBindingPort] = None,
) -> Optional[ModerationActor]:
    """
    解析应被警告/封禁的真人用户。
    1. guest_bot_caller_user → 归责并写入绑定
    2. 机器人消息 + 历史绑定 → 继续归责绑定用户
    3. 普通用户 → from_user
    4. 无绑定的机器人 → None
    """
    chat_id = message.chat.id
    caller: Optional[User] = getattr(message, "guest_bot_caller_user", None)
    bot_user = message.from_user

    if caller and not caller.is_bot and bot_user and bot_user.is_bot:
        username, mention, display = _labels(caller)
        logger.info(
            "访客机器人归责(含caller): msg_id=%s bot_id=%s → caller_id=%s %s",
            message.message_id,
            bot_user.id,
            caller.id,
            caller.username or caller.first_name,
        )
        if bindings is not None:
            await bindings.bind_guest_bot_caller(
                chat_id, bot_user.id, caller.id, username
            )
        return ModerationActor(
            user_id=caller.id,
            username=username,
            mention=mention,
            display_name=display,
            via_guest_bot=True,
            bot_sender_id=bot_user.id,
            via_guest_binding=False,
        )

    if bot_user and bot_user.is_bot and bindings is not None:
        bound = await bindings.lookup_guest_bot_caller(chat_id, bot_user.id)
        if bound:
            caller_id, caller_name = bound
            logger.info(
                "访客机器人归责(历史绑定): msg_id=%s bot_id=%s → bound_caller_id=%s "
                "(本条无 guest_bot_caller_user)",
                message.message_id,
                bot_user.id,
                caller_id,
            )
            return _actor_from_user_id(
                caller_id,
                caller_name,
                via_guest_bot=True,
                bot_sender_id=bot_user.id,
                via_guest_binding=True,
            )
        logger.info(
            "普通机器人消息: msg_id=%s bot_id=%s username=%s "
            "(无 guest_bot_caller_user 且无历史绑定)",
            message.message_id,
            bot_user.id,
            bot_user.username or bot_user.first_name,
        )
        return None

    if bot_user and bot_user.is_bot:
        return None

    user = bot_user
    if not user:
        return None

    username, mention, display = _labels(user)
    return ModerationActor(
        user_id=user.id,
        username=username,
        mention=mention,
        display_name=display,
    )


async def moderation_subject_user_id(
    message: Message,
    bindings: Optional[GuestBotBindingPort] = None,
) -> Optional[int]:
    """忽略列表、预审 gate 等使用的用户 ID。"""
    actor = await resolve_moderation_actor(message, bindings)
    if actor:
        return actor.user_id
    if message.from_user:
        return message.from_user.id
    return None


def message_sent_by_other_bot(message: Message) -> bool:
    return bool(message.from_user and message.from_user.is_bot)
