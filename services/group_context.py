"""
为群聊对话生成「喵喵所在群 + 管理权限 + 能力说明」上下文，注入系统提示词。
"""
from typing import Optional

from aiogram import Bot
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner, Message

from services.moderation_tools import (
    ModerationToolContext,
    build_tools_system_addon,
)
from services import telegram_moderation as mod
from services.telegram_admin_perms import admin_has_perm


async def build_group_system_addon(
    bot: Bot,
    message: Message,
    *,
    use_tools: bool = False,
) -> str:
    """群聊时追加到 system_instruction 的说明（仅群/超级群）。"""
    if message.chat.type not in ("group", "supergroup"):
        return ""

    if use_tools:
        ctx = await ModerationToolContext.from_message(message)
        base = await _build_legacy_context(bot, message)
        tools_part = build_tools_system_addon(ctx)
        return f"{base}\n\n{tools_part}" if base else tools_part

    return await _build_legacy_context(bot, message)


async def _build_legacy_context(bot: Bot, message: Message) -> str:
    """基础群环境说明（不含 @@MOD / tools 细则）。"""
    chat = message.chat
    title = chat.title or "本群"
    chat_id = chat.id

    try:
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat_id, me.id)
    except Exception:
        return (
            f"【群聊环境】你正在 Telegram 群「{title}」中回复。"
            "无法读取本群权限，请勿承诺执行封禁/禁言。"
        )

    is_admin = isinstance(bot_member, (ChatMemberAdministrator, ChatMemberOwner))
    if not is_admin:
        return (
            f"【群聊环境】你正在 Telegram 群「{title}」(chat_id={chat_id}) 中作为普通成员活动。\n"
            "你没有群管理员权限，不能替群执行删消息、禁言、封禁。"
        )

    if isinstance(bot_member, ChatMemberOwner):
        role = "群主（机器人账号）"
    else:
        role = "群管理员（机器人）"

    perms = []
    if isinstance(bot_member, ChatMemberAdministrator):
        m = bot_member
        if admin_has_perm(m, "can_delete_messages"):
            perms.append("删除消息")
        if admin_has_perm(m, "can_restrict_members", "can_ban_users"):
            perms.append("限制成员(禁言)")
            perms.append("封禁/踢人")

    perm_text = "、".join(perms) if perms else "（未勾选删消息/禁言/封禁等）"

    requester = message.from_user
    requester_line = ""
    if requester and await mod.is_user_group_admin(chat_id, requester.id):
        requester_line = "当前发消息的用户是本群 Telegram 管理员。\n"

    reply_hint = ""
    if message.reply_to_message and message.reply_to_message.from_user:
        ru = message.reply_to_message.from_user
        reply_hint = (
            f"用户引用 message_id={message.reply_to_message.message_id}、"
            f"作者 user_id={ru.id}。\n"
        )

    return (
        f"【群聊环境】你正在 Telegram 超级群「{title}」(chat_id={chat_id}) 中回复。\n"
        f"身份：{role}；Telegram 权限：{perm_text}。\n"
        f"{requester_line}{reply_hint}"
    )
