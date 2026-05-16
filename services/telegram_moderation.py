"""
Telegram 群管能力抽象层（供 Bot 处理器、MCP 工具等共用）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from aiogram import Bot
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner

from config.settings import TOKEN
from services.group_admin import group_admin

_bot: Optional[Bot] = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        if not TOKEN:
            raise RuntimeError("TG_BOT_TOKEN 未配置")
        _bot = Bot(token=TOKEN)
    return _bot


async def ensure_group_admin_db() -> None:
    if not group_admin.async_init_done:
        await group_admin.init_db()


async def get_group_capabilities(chat_id: int) -> Dict[str, Any]:
    """查询机器人在群内的角色与权限（结构化）。"""
    await ensure_group_admin_db()
    bot = get_bot()
    me = await bot.get_me()

    out: Dict[str, Any] = {
        "chat_id": chat_id,
        "bot_id": me.id,
        "bot_username": me.username,
        "is_bot_admin": False,
        "role": "member",
        "permissions": [],
        "can_moderate": False,
    }

    try:
        member = await bot.get_chat_member(chat_id, me.id)
    except Exception as e:
        out["error"] = str(e)
        return out

    if isinstance(member, ChatMemberOwner):
        out["role"] = "owner"
        out["is_bot_admin"] = True
    elif isinstance(member, ChatMemberAdministrator):
        out["role"] = "administrator"
        out["is_bot_admin"] = True
        perms = []
        if member.can_delete_messages:
            perms.append("delete_messages")
        if member.can_restrict_members:
            perms.append("restrict_members")
        if member.can_ban_users:
            perms.append("ban_users")
        if member.can_pin_messages:
            perms.append("pin_messages")
        if member.can_manage_chat:
            perms.append("manage_chat")
        out["permissions"] = perms
    else:
        out["role"] = getattr(member, "status", "member")

    out["can_moderate"] = out["is_bot_admin"] and bool(
        set(out["permissions"]) & {"delete_messages", "restrict_members", "ban_users"}
    )
    return out


async def get_group_context_text(
    chat_id: int,
    *,
    requester_user_id: Optional[int] = None,
    reply_message_id: Optional[int] = None,
    reply_author_user_id: Optional[int] = None,
) -> str:
    """人类/模型可读的群环境与能力说明。"""
    bot = get_bot()
    caps = await get_group_capabilities(chat_id)

    try:
        chat = await bot.get_chat(chat_id)
        title = chat.title or str(chat_id)
    except Exception:
        title = str(chat_id)

    if caps.get("error"):
        return f"群「{title}」(chat_id={chat_id})：无法读取机器人权限（{caps['error']}）。"

    if not caps["is_bot_admin"]:
        return (
            f"群「{title}」(chat_id={chat_id})：喵喵是普通成员，无删消息/禁言/封禁权限。"
        )

    perm_cn = {
        "delete_messages": "删除消息",
        "restrict_members": "禁言",
        "ban_users": "封禁/踢人",
        "pin_messages": "置顶",
        "manage_chat": "管理群",
    }
    plabels = [perm_cn.get(p, p) for p in caps["permissions"]]
    perm_text = "、".join(plabels) if plabels else "无关键执法权限"

    lines = [
        f"群「{title}」(chat_id={chat_id})",
        f"喵喵身份：{caps['role']}；权限：{perm_text}",
        f"可执法：{'是' if caps['can_moderate'] else '否'}",
    ]

    if requester_user_id is not None:
        if await group_admin.is_admin(bot, chat_id, requester_user_id):
            lines.append(f"操作者 user_id={requester_user_id} 是本群 Telegram 管理员。")

    if reply_message_id is not None and reply_author_user_id is not None:
        lines.append(
            f"处置目标：message_id={reply_message_id} 的作者 user_id={reply_author_user_id}。"
        )

    return "\n".join(lines)


async def check_text_violation(chat_id: int, text: str) -> Optional[str]:
    """检查文本是否命中屏蔽词，返回 violation_type 或 None。"""
    await ensure_group_admin_db()
    if not text:
        return None
    return group_admin.check_keywords(chat_id, text)


async def is_user_group_admin(chat_id: int, user_id: int) -> bool:
    bot = get_bot()
    return await group_admin.is_admin(bot, chat_id, user_id)


async def delete_message(chat_id: int, message_id: int) -> bool:
    bot = get_bot()
    return await group_admin.delete_message(bot, chat_id, message_id)


async def warn_user(chat_id: int, user_id: int, reason: str = "") -> int:
    bot = get_bot()
    return await group_admin.warn_user(bot, chat_id, user_id, reason)


async def mute_user(
    chat_id: int, user_id: int, hours: int = 24, reason: str = ""
) -> bool:
    bot = get_bot()
    hours = max(1, min(int(hours), 168))
    until = datetime.now() + timedelta(hours=hours)
    return await group_admin.mute_user(bot, chat_id, user_id, until)


async def ban_user(
    chat_id: int,
    user_id: int,
    reason: str = "",
    banned_by: int = 0,
) -> bool:
    bot = get_bot()
    return await group_admin.ban_user(bot, chat_id, user_id, reason, banned_by)


async def kick_user(chat_id: int, user_id: int, reason: str = "") -> bool:
    bot = get_bot()
    return await group_admin.kick_user(bot, chat_id, user_id, reason)


async def unban_user(chat_id: int, user_id: int) -> bool:
    bot = get_bot()
    return await group_admin.unban_user(bot, chat_id, user_id)


async def add_keyword(chat_id: int, keyword: str) -> bool:
    await ensure_group_admin_db()
    return await group_admin.add_keyword(chat_id, keyword)


async def list_keywords(chat_id: int) -> List[str]:
    await ensure_group_admin_db()
    return await group_admin.list_keywords(chat_id)


async def get_violation_stats(chat_id: int, days: int = 7) -> Dict[str, Any]:
    await ensure_group_admin_db()
    return await group_admin.get_violation_stats(chat_id, days)


async def execute_moderation(
    chat_id: int,
    action: str,
    target_user_id: int,
    *,
    message_id: Optional[int] = None,
    hours: int = 24,
    reason: str = "",
    operator_user_id: int = 0,
    require_operator_admin: bool = True,
    allow_if_target_text_is_spam: bool = False,
    target_message_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    统一执行单条群管动作。
    require_operator_admin：要求 operator 为群管（MCP 调用建议 True）。
    allow_if_target_text_is_spam：引用内容为广告/垃圾时可不要求 operator 为群管。
    """
    action = (action or "").lower().strip()
    result: Dict[str, Any] = {
        "ok": False,
        "action": action,
        "chat_id": chat_id,
        "target_user_id": target_user_id,
        "message": "",
    }

    caps = await get_group_capabilities(chat_id)
    if not caps.get("can_moderate"):
        result["message"] = "喵喵在该群无管理权限或未勾选删消息/禁言/封禁"
        return result

    bot = get_bot()
    if await group_admin.is_admin(bot, chat_id, target_user_id):
        result["message"] = "不能对群管理员执行该操作"
        return result

    allowed = True
    if require_operator_admin and operator_user_id:
        if not await group_admin.is_admin(bot, chat_id, operator_user_id):
            if allow_if_target_text_is_spam and target_message_text:
                if group_admin.check_keywords(chat_id, target_message_text) is None:
                    allowed = False
            else:
                allowed = False
    if not allowed:
        result["message"] = "操作者非群管理员，且不满足自动处置条件"
        return result

    try:
        if action == "del":
            if message_id is None:
                result["message"] = "删除消息需要 message_id"
                return result
            ok = await delete_message(chat_id, message_id)
            result["ok"] = ok
            result["message"] = "已删除消息" if ok else "删除失败"
        elif action == "warn":
            n = await warn_user(chat_id, target_user_id, reason or "违规")
            result["ok"] = True
            result["message"] = f"已警告，累计 {n} 次"
            result["warning_count"] = n
        elif action == "mute":
            ok = await mute_user(chat_id, target_user_id, hours, reason)
            result["ok"] = ok
            result["message"] = f"已禁言 {hours} 小时" if ok else "禁言失败"
        elif action == "ban":
            ok = await ban_user(
                chat_id, target_user_id, reason or "违规", banned_by=operator_user_id
            )
            result["ok"] = ok
            result["message"] = "已封禁" if ok else "封禁失败"
        elif action == "kick":
            ok = await kick_user(chat_id, target_user_id, reason or "踢出")
            result["ok"] = ok
            result["message"] = "已踢出" if ok else "踢出失败"
        elif action == "unban":
            ok = await unban_user(chat_id, target_user_id)
            result["ok"] = ok
            result["message"] = "已解封" if ok else "解封失败"
        else:
            result["message"] = f"未知动作: {action}"
    except Exception as e:
        result["message"] = str(e)

    return result
