"""
群组管理命令处理器模块
处理 /ban, /unban, /kick, /warn, /mute, /del, /stats 等命令
"""
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message

from config.group_admin_help import GROUP_ADMIN_HELP_HTML
from config.settings import bot

# 导入群组管理模块
from services.group_admin import group_admin

router = Router()


@router.message(F.text.in_({"/grouphelp", "/modhelp", "/adminhelp"}))
async def group_help_command(message: Message):
    """群管命令完整说明（群内人人可看，执行仍需管理员权限）。"""
    if message.chat.type not in ("group", "supergroup", "private"):
        return
    await message.answer(GROUP_ADMIN_HELP_HTML, parse_mode="HTML", disable_web_page_preview=True)


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


@router.message(F.text.startswith("/listspam"))
async def listspam_command(message: Message):
    """查看广告记录（bayes_spam_sniper /listspam）。"""
    from services.group_admin.bayes_spam import spam_log

    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type not in ("group", "supergroup"):
        return
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    if not group_admin.async_init_done:
        await group_admin.init_db()

    limit = 10
    parts = (message.text or "").split()
    if len(parts) > 1:
        try:
            limit = max(1, min(int(parts[1]), 30))
        except ValueError:
            pass

    entries = await spam_log.list_recent(chat_id, limit=limit)
    if not entries:
        await message.reply("📭 暂无广告记录。漏网可回复消息使用 /markspam。")
        return

    lines = [f"<b>📋 近期广告记录（最近 {len(entries)} 条）</b>\n"]
    for e in entries:
        preview = e.message_text.replace("\n", " ")[:120]
        who = f"@{e.username}" if e.username else f"uid:{e.user_id}"
        lines.append(
            f"\n<b>#{e.id}</b> · p={e.p_spam:.2f} · {e.label} · {who}\n"
            f"<code>{preview}</code>"
        )
    lines.append(
        "\n\n误杀请发：<code>/markham &lt;编号&gt;</code>\n"
        "漏网请回复该消息：<code>/markspam</code>"
    )
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(F.text.startswith("/listbanuser"))
async def listbanuser_command(message: Message):
    """查看封禁列表（bayes_spam_sniper /listbanuser）。"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type not in ("group", "supergroup"):
        return
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    if not group_admin.async_init_done:
        await group_admin.init_db()

    banned = await group_admin.list_banned_users(chat_id)
    if not banned:
        await message.reply("📭 当前没有封禁记录。")
        return

    lines = [f"<b>🚫 封禁列表（{len(banned)} 条）</b>\n"]
    for row in banned:
        desc = await group_admin.describe_banned_member(
            bot, chat_id, row["user_id"]
        )
        lines.append(group_admin.format_ban_list_line(row, desc))
    lines.append(
        "\n解封：回复该用户/机器人消息，发送 <code>/unban</code>"
    )
    await message.reply("\n".join(lines), parse_mode="HTML")


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


def _user_display_name(user) -> str:
    return " ".join(
        filter(None, [getattr(user, "first_name", None), getattr(user, "last_name", None)])
    ).strip() or getattr(user, "username", None) or ""


@router.message(F.text.startswith("/markspam"))
async def markspam_command(message: Message):
    """回复违规消息：训练为广告、删除并封禁（参考 bayes_spam_sniper /markspam）。"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type not in ("group", "supergroup"):
        return
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    if not message.reply_to_message:
        await message.reply("⚠️ 请回复要标记为广告的消息")
        return

    if not group_admin.async_init_done:
        await group_admin.init_db()

    target = message.reply_to_message
    body = (target.text or target.caption or "").strip()
    if not body:
        await message.reply("⚠️ 该消息没有可训练的文本")
        return

    from config.performance import SPAM_ESCALATE_ACTION
    from services.group_admin.bayes_spam import spam_log
    from utils.moderation_actor import resolve_moderation_actor

    actor = await resolve_moderation_actor(target, group_admin)
    log_user_id = actor.user_id if actor else (
        target.from_user.id if target.from_user else None
    )
    log_username = (
        actor.username
        if actor
        else (
            (target.from_user.username or target.from_user.first_name)
            if target.from_user
            else ""
        )
    )

    await group_admin.train_bayes_spam(
        body, chat_id=chat_id, user_id=log_user_id
    )
    await spam_log.log_detection(
        chat_id=chat_id,
        message_id=target.message_id,
        user_id=log_user_id,
        username=log_username,
        message_text=body,
        p_spam=1.0,
        label=spam_log.LABEL_SPAM,
        source=spam_log.SOURCE_MARKSPAM,
    )

    ban_notes: list[str] = []
    if actor:
        await group_admin.ban_user(
            bot,
            chat_id,
            actor.user_id,
            "管理员 /markspam",
            banned_by=user_id,
        )
        ban_notes.append(f"真人 @{actor.username}（<code>{actor.user_id}</code>）")
        if actor.bot_sender_id:
            bot_note = await group_admin._remove_associated_spam_bot(
                bot,
                chat_id,
                actor.bot_sender_id,
                "管理员 /markspam",
                use_ban=SPAM_ESCALATE_ACTION == "ban",
            )
            if bot_note:
                ban_notes.append(bot_note)
    elif target.from_user:
        fu = target.from_user
        await group_admin.ban_user(
            bot, chat_id, fu.id, "管理员 /markspam", banned_by=user_id
        )
        name = fu.username or fu.first_name or str(fu.id)
        if fu.is_bot:
            ban_notes.append(
                f"机器人 @{name}（<code>{fu.id}</code>，未绑定真人）"
            )
        else:
            ban_notes.append(f"@{name}（<code>{fu.id}</code>）")

    await group_admin.delete_message(bot, chat_id, target.message_id)
    try:
        await message.delete()
    except Exception:
        pass
    detail = "；".join(ban_notes) if ban_notes else "（无封禁对象）"
    await bot.send_message(
        chat_id,
        f"✅ 已标记为广告并训练模型。封禁：{detail}",
        parse_mode="HTML",
    )


@router.message(F.text.startswith("/markham"))
async def markham_command(message: Message):
    """标为正常：/markham <listspam编号> 或回复消息（等同 BSS listspam 标正常）。"""
    from services.group_admin.bayes_spam import spam_log

    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type not in ("group", "supergroup"):
        return
    if not await group_admin.is_admin(bot, chat_id, user_id):
        await message.reply("❌ 您没有管理员权限")
        return
    if not group_admin.async_init_done:
        await group_admin.init_db()

    parts = (message.text or "").split()
    body: str | None = None
    if len(parts) >= 2 and parts[1].isdigit():
        body = await spam_log.mark_log_as_ham(int(parts[1]), chat_id)
        if not body:
            await message.reply("⚠️ 未找到该编号记录，请先 /listspam 查看编号")
            return
    elif message.reply_to_message:
        body = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()
        if not body:
            await message.reply("⚠️ 该消息没有可训练的文本")
            return
    else:
        await message.reply(
            "用法：\n• <code>/markham 12</code> — 配合 /listspam 的 #编号\n"
            "• 回复某条消息 — 将该内容标为正常",
            parse_mode="HTML",
        )
        return

    await group_admin.train_bayes_ham(body, chat_id=chat_id)
    await message.reply("✅ 已标为正常并训练模型，类似内容不易再被判为广告")


@router.message(F.text.startswith("/feedspam"))
async def feedspam_command(message: Message):
    """投喂广告样本文本训练（无需回复消息）。"""
    import logging

    chat_id = message.chat.id
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply("用法：/feedspam 广告文本内容…")
        return

    try:
        if not group_admin.async_init_done:
            await group_admin.init_db()

        text = parts[1].strip()
        scope_chat = chat_id if message.chat.type in ("group", "supergroup") else None
        await group_admin.train_bayes_spam(text, chat_id=scope_chat)
        await message.reply("✅ 已投喂广告样本（全局与本群模型已更新）")
    except Exception as e:
        logging.exception("feedspam 失败")
        await message.reply(f"❌ 投喂失败：{e}")

