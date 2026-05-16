"""
群组管理命令处理器模块
处理 /ban, /unban, /kick, /warn, /mute, /del, /stats 等命令
"""
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message

from config.settings import bot

# 导入群组管理模块
from services.group_admin import group_admin

router = Router()


@router.message(F.text.startswith("/ban"))
async def ban_user_command(message: Message):
    """封禁用户命令"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ["group", "supergroup"]:
        return
    
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    
    if not group_admin.async_init_done:
        await group_admin.init_db()
    
    target_user = None
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    elif message.text:
        parts = message.text.split()
        if len(parts) > 1:
            await message.reply("⚠️ 请回复要封禁的用户消息，或使用 /ban [回复消息]")
            return
    
    if not target_user:
        await message.reply("⚠️ 请回复要封禁的用户消息")
        return
    
    if target_user.id == user_id:
        await message.reply("❌ 不能封禁自己")
        return
    
    reason = " ".join(message.text.split()[2:]) if len(message.text.split()) > 2 else "管理员封禁"
    success = await group_admin.ban_user(bot, chat_id, target_user.id, reason, user_id)
    
    if success:
        await message.reply(f"✅ 用户 @{target_user.username or target_user.first_name} 已被封禁\n原因: {reason}")
    else:
        await message.reply("❌ 封禁失败，请确保机器人有管理员权限")


@router.message(F.text.startswith("/unban"))
async def unban_user_command(message: Message):
    """解封用户命令"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ["group", "supergroup"]:
        return
    
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    
    if not group_admin.async_init_done:
        await group_admin.init_db()
    
    target_user = None
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    
    if not target_user:
        await message.reply("⚠️ 请回复要解封的用户消息")
        return
    
    success = await group_admin.unban_user(bot, chat_id, target_user.id)
    
    if success:
        await message.reply(f"✅ 用户 @{target_user.username or target_user.first_name} 已被解封")
    else:
        await message.reply("❌ 解封失败")


@router.message(F.text.startswith("/kick"))
async def kick_user_command(message: Message):
    """踢出用户命令"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ["group", "supergroup"]:
        return
    
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    
    if not group_admin.async_init_done:
        await group_admin.init_db()
    
    target_user = None
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    
    if not target_user:
        await message.reply("⚠️ 请回复要踢出的用户消息")
        return
    
    if target_user.id == user_id:
        await message.reply("❌ 不能踢出自己")
        return
    
    reason = " ".join(message.text.split()[2:]) if len(message.text.split()) > 2 else "管理员踢出"
    success = await group_admin.kick_user(bot, chat_id, target_user.id, reason)
    
    if success:
        await message.reply(f"✅ 用户 @{target_user.username or target_user.first_name} 已被踢出\n原因: {reason}")
    else:
        await message.reply("❌ 踢出失败")


@router.message(F.text.startswith("/warn"))
async def warn_user_command(message: Message):
    """警告用户命令"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ["group", "supergroup"]:
        return
    
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    
    if not group_admin.async_init_done:
        await group_admin.init_db()
    
    target_user = None
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    
    if not target_user:
        await message.reply("⚠️ 请回复要警告的用户消息")
        return
    
    reason = " ".join(message.text.split()[2:]) if len(message.text.split()) > 2 else "管理员警告"
    warning_count = await group_admin.warn_user(bot, chat_id, target_user.id, reason)
    
    await message.reply(
        f"⚠️ 用户 @{target_user.username or target_user.first_name} 收到警告 {warning_count} 次\n"
        f"原因: {reason}"
    )


@router.message(F.text.startswith("/mute"))
async def mute_user_command(message: Message):
    """禁言用户命令"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ["group", "supergroup"]:
        return
    
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    
    if not group_admin.async_init_done:
        await group_admin.init_db()
    
    target_user = None
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    
    if not target_user:
        await message.reply("⚠️ 请回复要禁言的用户消息")
        return
    
    hours = 1
    parts = message.text.split()
    if len(parts) > 1:
        try:
            hours = int(parts[1])
            hours = max(1, min(hours, 168))
        except ValueError:
            pass
    
    until_date = datetime.now() + timedelta(hours=hours)
    success = await group_admin.mute_user(bot, chat_id, target_user.id, until_date)
    
    if success:
        await message.reply(f"🔇 用户 @{target_user.username or target_user.first_name} 已被禁言 {hours} 小时")
    else:
        await message.reply("❌ 禁言失败")


@router.message(F.text.startswith("/del"))
async def delete_message_command(message: Message):
    """删除消息命令"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ["group", "supergroup"]:
        return
    
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    
    if message.reply_to_message:
        success = await group_admin.delete_message(bot, chat_id, message.reply_to_message.message_id)
        if success:
            await message.delete()
        else:
            await message.reply("❌ 删除失败")
    else:
        await message.reply("⚠️ 请回复要删除的消息")


@router.message(F.text.startswith("/stats"))
async def violation_stats_command(message: Message):
    """违规统计命令"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ["group", "supergroup"]:
        return
    
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    
    if not group_admin.async_init_done:
        await group_admin.init_db()
    
    days = 7
    parts = message.text.split()
    if len(parts) > 1:
        try:
            days = int(parts[1])
            days = max(1, min(days, 30))
        except ValueError:
            pass
    
    stats = await group_admin.get_violation_stats(chat_id, days)
    
    stats_text = (
        f"📊 <b>违规统计（最近 {days} 天）</b>\n\n"
        f"总违规数: <b>{stats['total']}</b>\n"
        f"诈骗信息: <b>{stats['scam']}</b>\n"
        f"色情内容: <b>{stats['porno']}</b>\n"
        f"垃圾信息: <b>{stats['spam']}</b>"
    )
    
    await message.reply(stats_text, parse_mode="HTML")


@router.message(F.text.startswith("/kwadd"))
async def keyword_add_command(message: Message):
    """添加屏蔽词"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type not in ["group", "supergroup", "channel"]:
        await message.reply("⚠️ 该命令仅支持在群组/频道中使用。")
        return

    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return

    if not group_admin.async_init_done:
        await group_admin.init_db()

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply("用法：/kwadd 关键词")
        return

    keyword = parts[1].strip()
    added = await group_admin.add_keyword(chat_id, keyword)
    if added:
        await message.reply(f"✅ 已添加屏蔽词：<code>{keyword}</code>", parse_mode="HTML")
    else:
        await message.reply(f"ℹ️ 屏蔽词已存在或无效：<code>{keyword}</code>", parse_mode="HTML")


@router.message(F.text.startswith("/kwdel"))
async def keyword_del_command(message: Message):
    """删除屏蔽词"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type not in ["group", "supergroup", "channel"]:
        await message.reply("⚠️ 该命令仅支持在群组/频道中使用。")
        return

    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return

    if not group_admin.async_init_done:
        await group_admin.init_db()

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply("用法：/kwdel 关键词")
        return

    keyword = parts[1].strip()
    removed = await group_admin.remove_keyword(chat_id, keyword)
    if removed:
        await message.reply(f"✅ 已删除屏蔽词：<code>{keyword}</code>", parse_mode="HTML")
    else:
        await message.reply(f"ℹ️ 未找到该自定义屏蔽词：<code>{keyword}</code>", parse_mode="HTML")


@router.message(F.text == "/kwlist")
async def keyword_list_command(message: Message):
    """查看自定义屏蔽词"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type not in ["group", "supergroup", "channel"]:
        await message.reply("⚠️ 该命令仅支持在群组/频道中使用。")
        return

    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return

    if not group_admin.async_init_done:
        await group_admin.init_db()

    keywords = await group_admin.list_keywords(chat_id)
    if not keywords:
        await message.reply("当前没有自定义屏蔽词（默认内置关键词仍会生效）。")
        return

    body = "\n".join([f"- <code>{kw}</code>" for kw in keywords])
    await message.reply(f"📋 当前自定义屏蔽词（仅本群/频道生效）：\n{body}", parse_mode="HTML")


# ==================== 忽略用户命令 ====================

@router.message(F.text.startswith("/ignore"))
async def ignore_user_command(message: Message):
    """忽略用户命令：/ignore [回复消息]"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # 检查是否是 /ignorelist 命令，避免冲突
    if message.text and message.text.strip() == "/ignorelist":
        return
    
    if message.chat.type not in ["group", "supergroup"]:
        await message.reply("⚠️ 该命令仅支持在群组中使用。")
        return
    
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    
    if not group_admin.async_init_done:
        await group_admin.init_db()
    
    target_user = None
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    
    if not target_user:
        await message.reply("⚠️ 请回复要忽略的用户消息\n用法：回复某用户的消息后发送 /ignore")
        return
    
    # 检查是否试图忽略管理员
    if await group_admin.is_admin(bot, chat_id, target_user.id):
        await message.reply("❌ 不能忽略管理员")
        return
    
    # 检查是否已经被忽略
    if group_admin.is_ignored(chat_id, target_user.id):
        await message.reply(f"ℹ️ 用户 @{target_user.username or target_user.first_name} 已在忽略列表中")
        return
    
    success = await group_admin.ignore_user(chat_id, target_user.id, user_id)
    
    if success:
        await message.reply(
            f"🙈 已忽略用户 @{target_user.username or target_user.first_name}\n"
            f"机器人将不再回复该用户的消息"
        )
    else:
        await message.reply("❌ 忽略用户失败")


@router.message(F.text.startswith("/unignore"))
async def unignore_user_command(message: Message):
    """取消忽略用户命令：/unignore [回复消息]"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ["group", "supergroup"]:
        await message.reply("⚠️ 该命令仅支持在群组中使用。")
        return
    
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    
    if not group_admin.async_init_done:
        await group_admin.init_db()
    
    target_user = None
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    
    if not target_user:
        await message.reply("⚠️ 请回复要取消忽略的用户消息\n用法：回复某用户的消息后发送 /unignore")
        return
    
    # 检查是否在忽略列表中
    if not group_admin.is_ignored(chat_id, target_user.id):
        await message.reply(f"ℹ️ 用户 @{target_user.username or target_user.first_name} 不在忽略列表中")
        return
    
    success = await group_admin.unignore_user(chat_id, target_user.id)
    
    if success:
        await message.reply(
            f"👀 已取消忽略用户 @{target_user.username or target_user.first_name}\n"
            f"机器人将正常回复该用户的消息"
        )
    else:
        await message.reply("❌ 取消忽略失败")


@router.message(F.text == "/ignorelist")
async def ignore_list_command(message: Message):
    """查看被忽略的用户列表"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if message.chat.type not in ["group", "supergroup"]:
        await message.reply("⚠️ 该命令仅支持在群组中使用。")
        return
    
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    
    if not group_admin.async_init_done:
        await group_admin.init_db()
    
    ignored_users = await group_admin.list_ignored_users(chat_id)
    
    if not ignored_users:
        await message.reply("📋 当前没有被忽略的用户")
        return
    
    # 尝试获取用户名
    user_list = []
    for uid in ignored_users:
        try:
            member = await bot.get_chat_member(chat_id, uid)
            username = member.user.username or member.user.first_name or str(uid)
            user_list.append(f"- @{username} (ID: <code>{uid}</code>)")
        except Exception:
            user_list.append(f"- ID: <code>{uid}</code>")
    
    body = "\n".join(user_list)
    await message.reply(
        f"🙈 <b>被忽略的用户列表</b>（共 {len(ignored_users)} 人）：\n\n{body}",
        parse_mode="HTML"
    )

