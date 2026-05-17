"""
群组管理模块：贝叶斯广告拦截（bayes_spam_sniper）+ 封禁/忽略等。
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import List, Set, Optional, Dict

import aiosqlite
from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner, ChatPermissions

# 不再使用连接池，直接使用 aiosqlite.connect()

logger = logging.getLogger(__name__)

from services.group_admin.repo import DB_FILE

# 兼容旧 import（关键词模块已停用，仅保留符号）
ALL_BANNED_KEYWORDS: list = []


class GroupAdmin:
    """群组管理类"""
    
    def __init__(self):
        self.user_warnings: Dict[int, int] = {}  # {user_id: warning_count}
        # 各群内已封禁用户 {chat_id: {user_id, ...}}
        self.banned_users: Dict[int, Set[int]] = {}
        # 每个 chat 的被忽略用户集合 {chat_id: {user_id, ...}}
        self.ignored_users: Dict[int, Set[int]] = {}
        self.async_init_done = False
    
    async def init_db(self):
        """初始化数据库"""
        if self.async_init_done:
            return

        DB_FILE.parent.mkdir(parents=True, exist_ok=True)

        # 直接创建连接，不使用连接池（SQLite 连接开销小）
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            # 创建违规记录表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    message_text TEXT,
                    violation_type TEXT,
                    action_taken TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建封禁用户表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS banned_users (
                    user_id INTEGER PRIMARY KEY,
                    chat_id INTEGER,
                    reason TEXT,
                    banned_by INTEGER,
                    banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    unbanned_at TIMESTAMP
                )
            """)
            
            # 创建警告记录表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    warning_count INTEGER DEFAULT 1,
                    last_warning_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建用户图像发送记录表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_image_sends (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    first_image_sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id)
                )
            """)

            # 创建每个 chat 的自定义屏蔽词表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_banned_keywords (
                    chat_id INTEGER NOT NULL,
                    keyword TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, keyword)
                )
            """)
            
            # 创建被忽略用户表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ignored_users (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    ignored_by INTEGER,
                    ignored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id)
                )
            """)
            
            await conn.commit()
        
        # 加载已封禁用户（按群）
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT chat_id, user_id FROM banned_users WHERE unbanned_at IS NULL"
            ) as cursor:
                rows = await cursor.fetchall()
                banned: Dict[int, Set[int]] = {}
                for chat_id, user_id in rows:
                    if chat_id is None:
                        continue
                    banned.setdefault(int(chat_id), set()).add(int(user_id))
                self.banned_users = banned

        # 加载被忽略用户（按 chat 聚合到内存缓存）
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT chat_id, user_id FROM ignored_users") as cursor:
                rows = await cursor.fetchall()
                ignored_map: Dict[int, Set[int]] = {}
                for chat_id, user_id in rows:
                    ignored_map.setdefault(int(chat_id), set()).add(int(user_id))
                self.ignored_users = ignored_map
        
        self.async_init_done = True
        logger.info("群组管理数据库初始化完成")
    
    def is_user_banned_in_chat(self, chat_id: int, user_id: int) -> bool:
        return user_id in self.banned_users.get(chat_id, set())

    async def is_admin(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        """检查用户是否为管理员"""
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
        except Exception as e:
            logger.error(f"检查管理员权限失败: {e}")
            return False
    
    async def is_bot_admin(self, bot: Bot, chat_id: int) -> bool:
        """检查机器人是否为管理员"""
        try:
            bot_member = await bot.get_chat_member(chat_id, bot.id)
            return isinstance(bot_member, (ChatMemberAdministrator, ChatMemberOwner))
        except Exception as e:
            logger.error(f"检查机器人管理员权限失败: {e}")
            return False
    
    async def check_bayes_spam(
        self,
        chat_id: int,
        text: str,
        *,
        user_display_name: str = "",
    ) -> Optional[float]:
        """贝叶斯判定为广告时返回 spam 概率，否则 None。"""
        from services.group_admin.bayes_spam import get_detector

        result = await get_detector().classify_message(
            text,
            chat_id=chat_id,
            user_display_name=user_display_name,
        )
        if result.is_spam:
            return result.p_spam
        return None

    async def train_bayes_spam(
        self,
        text: str,
        *,
        chat_id: Optional[int],
        user_id: Optional[int] = None,
        training_target: str = "message_content",
    ) -> None:
        from services.group_admin.bayes_spam import get_detector

        await get_detector().train_spam(
            text,
            chat_id=chat_id,
            user_id=user_id,
            training_target=training_target,
        )

    async def train_bayes_ham(
        self,
        text: str,
        *,
        chat_id: Optional[int],
        user_id: Optional[int] = None,
        training_target: str = "message_content",
    ) -> None:
        from services.group_admin.bayes_spam import get_detector

        await get_detector().train_ham(
            text,
            chat_id=chat_id,
            user_id=user_id,
            training_target=training_target,
        )
    
    async def _send_group_notice(self, bot: Bot, chat_id: int, text: str) -> bool:
        """发送群管提示，遇 Flood 时等待后重试一次。"""
        for attempt in range(2):
            try:
                await bot.send_message(chat_id, text)
                return True
            except TelegramRetryAfter as e:
                if attempt == 0:
                    logger.warning(
                        "群管提示触发 Flood，%ss 后重试 chat_id=%s",
                        e.retry_after,
                        chat_id,
                    )
                    await asyncio.sleep(float(e.retry_after) + 0.5)
                    continue
                logger.error("群管提示 Flood 重试仍失败: %s", e)
                return False
            except Exception as e:
                logger.error(
                    "发送群管提示失败 chat_id=%s: %s: %s",
                    chat_id,
                    type(e).__name__,
                    e,
                )
                return False
        return False

    async def _notify_spam_warning(
        self,
        bot: Bot,
        message: types.Message,
        chat_id: int,
        notice: str,
    ) -> bool:
        """优先发群公告（不依赖原消息），失败再尝试 reply。"""
        if await self._send_group_notice(bot, chat_id, notice):
            return True
        for attempt in range(2):
            try:
                await message.reply(notice, allow_sending_without_reply=True)
                return True
            except TelegramRetryAfter as e:
                if attempt == 0:
                    await asyncio.sleep(float(e.retry_after) + 0.5)
                    continue
                logger.warning("回复警告 Flood 失败: %s", e)
            except Exception as e:
                logger.warning("回复警告失败: %s", e)
                break
        return False

    async def delete_message(self, bot: Bot, chat_id: int, message_id: int) -> bool:
        """删除消息"""
        try:
            await bot.delete_message(chat_id, message_id)
            return True
        except TelegramBadRequest as e:
            logger.warning(f"删除消息失败: {e}")
            return False
        except Exception as e:
            logger.error(f"删除消息异常: {e}")
            return False
    
    async def ban_user(self, bot: Bot, chat_id: int, user_id: int, reason: str = "", banned_by: int = 0) -> bool:
        """封禁用户"""
        try:
            # 检查机器人权限
            if not await self.is_bot_admin(bot, chat_id):
                logger.warning(f"机器人不是管理员，无法封禁用户 {user_id}")
                return False
            
            # 封禁用户
            await bot.ban_chat_member(chat_id, user_id)
            
            # 记录到数据库
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("""
                    INSERT OR REPLACE INTO banned_users (user_id, chat_id, reason, banned_by, banned_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, chat_id, reason, banned_by, datetime.now()))
                await conn.commit()
            
            self.banned_users.setdefault(chat_id, set()).add(user_id)
            logger.info(f"用户 {user_id} 已被封禁，原因: {reason}")
            return True
        except Exception as e:
            logger.error(f"封禁用户失败: {e}")
            return False
    
    async def unban_user(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        """解封用户"""
        try:
            if not await self.is_bot_admin(bot, chat_id):
                return False
            
            await bot.unban_chat_member(chat_id, user_id)
            
            # 更新数据库
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("""
                    UPDATE banned_users 
                    SET unbanned_at = ? 
                    WHERE user_id = ? AND chat_id = ?
                """, (datetime.now(), user_id, chat_id))
                await conn.commit()
            
            self.banned_users.get(chat_id, set()).discard(user_id)
            logger.info(f"用户 {user_id} 已被解封")
            return True
        except Exception as e:
            logger.error(f"解封用户失败: {e}")
            return False
    
    async def kick_user(self, bot: Bot, chat_id: int, user_id: int, reason: str = "") -> bool:
        """踢出用户（可以重新加入）"""
        try:
            if not await self.is_bot_admin(bot, chat_id):
                return False
            
            await bot.ban_chat_member(chat_id, user_id)
            # 立即解封，这样用户就可以重新加入
            await asyncio.sleep(1)
            await bot.unban_chat_member(chat_id, user_id)
            
            logger.info(f"用户 {user_id} 已被踢出，原因: {reason}")
            return True
        except Exception as e:
            logger.error(f"踢出用户失败: {e}")
            return False
    
    async def mute_user(self, bot: Bot, chat_id: int, user_id: int, until_date: datetime = None) -> bool:
        """禁言用户"""
        try:
            if not await self.is_bot_admin(bot, chat_id):
                return False

            if await self.is_admin(bot, chat_id, user_id):
                logger.warning(f"不能禁言管理员 {user_id}")
                return False

            if until_date is None:
                until_date = datetime.now() + timedelta(hours=1)

            permissions = ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            )
            await bot.restrict_chat_member(
                chat_id,
                user_id,
                permissions=permissions,
                until_date=until_date,
            )
            logger.info(f"用户 {user_id} 已被禁言至 {until_date}")
            return True
        except Exception as e:
            logger.error(f"禁言用户失败: {e}")
            return False
    
    async def warn_user(self, bot: Bot, chat_id: int, user_id: int, reason: str = "") -> int:
        """警告用户，返回当前警告次数"""
        try:
            # 获取当前警告次数
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                async with conn.execute("""
                    SELECT warning_count FROM warnings 
                    WHERE chat_id = ? AND user_id = ?
                """, (chat_id, user_id)) as cursor:
                    row = await cursor.fetchone()
                    warning_count = (row[0] if row else 0) + 1
                
                # 更新或插入警告记录
                await conn.execute("""
                    INSERT OR REPLACE INTO warnings (chat_id, user_id, warning_count, last_warning_at)
                    VALUES (?, ?, ?, ?)
                """, (chat_id, user_id, warning_count, datetime.now()))
                await conn.commit()
            
            self.user_warnings[user_id] = warning_count
            logger.info(f"用户 {user_id} 收到警告 {warning_count} 次，原因: {reason}")
            return warning_count
        except Exception as e:
            logger.error(f"警告用户失败: {e}")
            return 0
    
    async def record_violation(
        self, 
        chat_id: int, 
        user_id: int, 
        username: str, 
        message_text: str, 
        violation_type: str, 
        action_taken: str
    ):
        """记录违规行为"""
        try:
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("""
                    INSERT INTO violations (chat_id, user_id, username, message_text, violation_type, action_taken)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (chat_id, user_id, username, message_text, violation_type, action_taken))
                await conn.commit()
        except Exception as e:
            logger.error(f"记录违规行为失败: {e}")
    
    async def handle_bayes_spam(
        self,
        bot: Bot,
        message: types.Message,
        *,
        p_spam: float,
        source: str = "auto",
    ) -> bool:
        """贝叶斯/规则判定为广告：删消息、记日志、警告；满额后再踢出/封禁。"""
        from config.performance import SPAM_BAN_THRESHOLD, SPAM_ESCALATE_ACTION
        from services.group_admin.bayes_spam import spam_log

        chat_id = message.chat.id
        user = message.from_user
        if not user:
            return False
        user_id = user.id
        username = user.username or user.first_name or str(user_id)
        message_text = (message.text or message.caption or "").strip()
        mention = f"@{username}" if username and not username.isdigit() else username
        is_tg_admin = await self.is_admin(bot, chat_id, user_id)

        if self.is_user_banned_in_chat(chat_id, user_id):
            notice = f"🚫 {mention} 已被封禁，本条广告已删除。"
            sent = await self._notify_spam_warning(bot, message, chat_id, notice)
            deleted = await self.delete_message(bot, chat_id, message.message_id)
            logger.info(
                "bayes spam 封禁用户复犯 chat_id=%s user=%s notice_sent=%s deleted=%s",
                chat_id,
                user_id,
                sent,
                deleted,
            )
            if not sent:
                logger.error(
                    "封禁用户广告警告未发出 chat_id=%s user=%s",
                    chat_id,
                    user_id,
                )
            return True

        label = (
            spam_log.LABEL_SPAM
            if source == spam_log.SOURCE_MARKSPAM
            else spam_log.LABEL_MAYBE_SPAM
        )
        await spam_log.log_detection(
            chat_id=chat_id,
            message_id=message.message_id,
            user_id=user_id,
            username=username,
            message_text=message_text,
            p_spam=p_spam,
            label=label,
            source=source,
        )

        warn_n = await self.warn_user(
            bot, chat_id, user_id, "发送广告或垃圾信息（自动检测）"
        )
        threshold = max(1, SPAM_BAN_THRESHOLD)

        if warn_n >= threshold:
            reason = f"累计广告警告 {warn_n} 次"
            if is_tg_admin:
                ok = False
                action_text = "群管理员无法被机器人踢出/封禁"
            elif SPAM_ESCALATE_ACTION == "ban":
                ok = await self.ban_user(
                    bot, chat_id, user_id, reason, banned_by=bot.id
                )
                action_text = "已封禁" if ok else "封禁失败（请检查机器人权限）"
            else:
                ok = await self.kick_user(bot, chat_id, user_id, reason)
                action_text = "已踢出群组" if ok else "踢出失败（请检查机器人权限）"
            notice = (
                f"🚫 {mention} 触发广告规则，"
                f"累计警告 {warn_n} 次（满 {threshold} 次），{action_text}。"
                "本条广告即将删除。"
            )
        else:
            remaining = threshold - warn_n
            notice = (
                f"⚠️ {mention} 触发广告规则，"
                f"第 {warn_n}/{threshold} 次警告，"
                f"再犯 {remaining} 次将{'封禁' if SPAM_ESCALATE_ACTION == 'ban' else '踢出'}。"
                "本条广告即将删除。"
            )
        if is_tg_admin:
            notice += "（发送者为群管理员，仍会删帖；满额后可能无法踢出/封禁该管理员。）"

        # 必须先提示再删帖，否则用户只看到消息消失
        sent = await self._notify_spam_warning(bot, message, chat_id, notice)
        deleted = await self.delete_message(bot, chat_id, message.message_id)
        if not deleted:
            logger.warning(
                "广告消息删除失败 chat_id=%s msg_id=%s",
                chat_id,
                message.message_id,
            )

        await self.record_violation(
            chat_id, user_id, username, message_text, "spam", "贝叶斯删除并警告"
        )

        logger.info(
            "bayes spam 处置 chat_id=%s user=%s p=%.3f warn=%s/%s notice_sent=%s deleted=%s text=%r",
            chat_id,
            user_id,
            p_spam,
            warn_n,
            threshold,
            sent,
            deleted,
            message_text[:80],
        )
        if not sent:
            logger.error(
                "广告警告未发出 chat_id=%s user=%s，请检查机器人发消息权限",
                chat_id,
                user_id,
            )
        return True

    async def handle_vision_image_violation(
        self,
        bot: Bot,
        message: types.Message,
        *,
        violation_type: str,
        reason: str,
        confidence: float,
    ) -> tuple[bool, str]:
        """
        视觉审核判定违规后的处置。返回 (是否已处置, 群内简短说明)。
        """
        user = message.from_user
        if not user:
            return False, ""
        chat_id = message.chat.id
        user_id = user.id
        username = user.username or user.first_name or str(user_id)

        caption = (message.caption or "").strip()
        log_text = caption or f"[图片审核 confidence={confidence:.2f}]"

        vtype = (violation_type or "other").lower()
        brief = ""

        if vtype == "porno":
            deleted = await self.delete_message(bot, chat_id, message.message_id)
            if not deleted:
                return False, ""
            await self.record_violation(
                chat_id, user_id, username, log_text, "porno", "视觉审核删除"
            )
            banned = await self.ban_user(
                bot, chat_id, user_id, reason or "色情图片", banned_by=bot.id
            )
            if banned:
                brief = (
                    f"🚫 已删除疑似色情图片，并封禁 @{username}。"
                    f"{('原因：' + reason) if reason else ''}"
                )
            else:
                brief = f"🚫 已删除疑似色情图片。{('原因：' + reason) if reason else ''}"
            await self._send_group_notice(bot, chat_id, brief.strip())
            return True, ""

        if vtype in ("spam", "gambling", "other"):
            # handle_bayes_spam 已删图并在群内发送警告/踢出说明
            await self.handle_bayes_spam(
                bot,
                message,
                p_spam=float(confidence),
                source="vision_image",
            )
            return True, ""

        if vtype == "scam":
            deleted = await self.delete_message(bot, chat_id, message.message_id)
            if not deleted:
                return False, ""
            await self.record_violation(
                chat_id, user_id, username, log_text, "scam", "视觉审核删除"
            )
            warn_n = await self.warn_user(
                bot, chat_id, user_id, reason or "疑似诈骗图片"
            )
            brief = (
                f"⚠️ 已删除疑似诈骗图片，@{username} 累计警告 {warn_n} 次。"
                f"{('原因：' + reason) if reason else ''}"
            )
            from config.group_image_moderation import GROUP_IMAGE_SCAM_WARN_BAN

            if warn_n >= GROUP_IMAGE_SCAM_WARN_BAN:
                if await self.ban_user(
                    bot, chat_id, user_id, "诈骗图片警告达上限", banned_by=bot.id
                ):
                    brief += f"\n🚫 已达 {GROUP_IMAGE_SCAM_WARN_BAN} 次警告，已封禁。"
            await self._send_group_notice(bot, chat_id, brief.strip())
            return True, ""

        return False, ""

    async def check_and_handle_message(self, bot: Bot, message: types.Message) -> bool:
        """仅贝叶斯广告识别（含 BSS 汉字空格规则），自动删消息。"""
        if message.chat.type not in ["group", "supergroup", "channel"]:
            return False

        message_text = (message.text or message.caption or "").strip()
        if not message_text:
            return False
        # 斜杠命令由 admin 等路由处理，避免误伤 /feedspam 等
        if message_text.startswith("/"):
            return False

        display = ""
        if message.from_user:
            display = " ".join(
                filter(
                    None,
                    [
                        message.from_user.first_name,
                        message.from_user.last_name,
                        message.from_user.username,
                    ],
                )
            )
        p_spam = await self.check_bayes_spam(
            message.chat.id, message_text, user_display_name=display
        )
        if p_spam is not None:
            logger.info(
                "bayes spam chat_id=%s p=%.4f text=%r",
                message.chat.id,
                p_spam,
                message_text[:120],
            )
            await self.handle_bayes_spam(bot, message, p_spam=p_spam)
            return True

        return False

    async def list_banned_users(self, chat_id: int) -> List[dict]:
        """本群封禁列表（供 /listbanuser）。"""
        if not self.async_init_done:
            await self.init_db()
        out: List[dict] = []
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                """
                SELECT user_id, reason, banned_at, banned_by
                FROM banned_users
                WHERE chat_id = ? AND unbanned_at IS NULL
                ORDER BY banned_at DESC
                """,
                (chat_id,),
            ) as cur:
                rows = await cur.fetchall()
        for uid, reason, banned_at, banned_by in rows:
            out.append(
                {
                    "user_id": uid,
                    "reason": reason or "",
                    "banned_at": banned_at,
                    "banned_by": banned_by,
                }
            )
        return out
    
    async def get_violation_stats(self, chat_id: int, days: int = 7) -> Dict:
        """获取违规统计"""
        try:
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                since_date = datetime.now() - timedelta(days=days)
                
                # 统计各类型违规数量
                async with conn.execute("""
                    SELECT violation_type, COUNT(*) as count
                    FROM violations
                    WHERE chat_id = ? AND created_at >= ?
                    GROUP BY violation_type
                """, (chat_id, since_date)) as cursor:
                    stats = {row[0]: row[1] for row in await cursor.fetchall()}
                
                # 统计总违规数
                async with conn.execute("""
                    SELECT COUNT(*) FROM violations
                    WHERE chat_id = ? AND created_at >= ?
                """, (chat_id, since_date)) as cursor:
                    total = (await cursor.fetchone())[0]
                
                return {
                    "total": total,
                    "scam": stats.get("scam", 0),
                    "porno": stats.get("porno", 0),
                    "spam": stats.get("spam", 0),
                    "days": days
                }
        except Exception as e:
            logger.error(f"获取违规统计失败: {e}")
            return {"total": 0, "scam": 0, "porno": 0, "spam": 0, "days": days}
    
    async def should_check_image(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        """
        检查是否需要检测图像
        返回 True 如果：
        1. 用户第一次在群组发图像
        2. 用户加入群组不足一周
        """
        try:
            # 初始化数据库
            if not self.async_init_done:
                await self.init_db()
            
            # 检查是否是第一次发图像
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                async with conn.execute("""
                    SELECT first_image_sent_at FROM user_image_sends
                    WHERE chat_id = ? AND user_id = ?
                """, (chat_id, user_id)) as cursor:
                    row = await cursor.fetchone()
                    if row is None:
                        # 第一次发图像，需要检测
                        return True
            
            # 检查用户加入群组的时间
            try:
                member = await bot.get_chat_member(chat_id, user_id)
                # 获取用户加入时间
                if hasattr(member, 'joined_date') and member.joined_date:
                    join_date = datetime.fromtimestamp(member.joined_date)
                    days_since_join = (datetime.now() - join_date).days
                    # 如果加入不足一周，需要检测
                    if days_since_join < 7:
                        return True
                # 如果没有 joined_date（可能是管理员或创建者），默认不检测
                return False
            except Exception as e:
                logger.error(f"获取用户加入时间失败: {e}")
                # 如果获取失败，为了不影响正常用户，不进行检测
                return False
            
        except Exception as e:
            logger.error(f"检查图像检测条件失败: {e}")
            # 出错时为了不影响正常用户，不进行检测
            return False
    
    async def record_image_sent(self, chat_id: int, user_id: int):
        """记录用户发送图像的时间（如果是第一次）"""
        try:
            if not self.async_init_done:
                await self.init_db()
            
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                # 使用 INSERT OR IGNORE 来避免重复插入
                await conn.execute("""
                    INSERT OR IGNORE INTO user_image_sends (chat_id, user_id, first_image_sent_at)
                    VALUES (?, ?, ?)
                """, (chat_id, user_id, datetime.now()))
                await conn.commit()
        except Exception as e:
            logger.error(f"记录图像发送时间失败: {e}")
    
    # ==================== 忽略用户功能 ====================
    
    def is_ignored(self, chat_id: int, user_id: int) -> bool:
        """检查用户是否被忽略（同步方法，用于快速检查）"""
        return user_id in self.ignored_users.get(chat_id, set())
    
    async def ignore_user(self, chat_id: int, user_id: int, ignored_by: int = 0) -> bool:
        """忽略某个用户，机器人不再回复该用户的消息"""
        try:
            if not self.async_init_done:
                await self.init_db()
            
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                cursor = await conn.execute(
                    "INSERT OR IGNORE INTO ignored_users (chat_id, user_id, ignored_by) VALUES (?, ?, ?)",
                    (chat_id, user_id, ignored_by),
                )
                await conn.commit()
            
            # 更新内存缓存
            self.ignored_users.setdefault(chat_id, set()).add(user_id)
            added = (cursor.rowcount or 0) > 0
            logger.info(f"chat_id={chat_id} 已忽略用户: {user_id} (added={added})")
            return True
        except Exception as e:
            logger.error(f"忽略用户失败 chat_id={chat_id}, user_id={user_id}: {e}")
            return False
    
    async def unignore_user(self, chat_id: int, user_id: int) -> bool:
        """取消忽略某个用户"""
        try:
            if not self.async_init_done:
                await self.init_db()
            
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                cursor = await conn.execute(
                    "DELETE FROM ignored_users WHERE chat_id = ? AND user_id = ?",
                    (chat_id, user_id),
                )
                await conn.commit()
            
            # 更新内存缓存
            if chat_id in self.ignored_users:
                self.ignored_users[chat_id].discard(user_id)
                if not self.ignored_users[chat_id]:
                    self.ignored_users.pop(chat_id, None)
            
            removed = (cursor.rowcount or 0) > 0
            logger.info(f"chat_id={chat_id} 已取消忽略用户: {user_id} (removed={removed})")
            return removed
        except Exception as e:
            logger.error(f"取消忽略用户失败 chat_id={chat_id}, user_id={user_id}: {e}")
            return False
    
    async def list_ignored_users(self, chat_id: int) -> List[int]:
        """列出某个 chat 中被忽略的用户ID列表"""
        if not self.async_init_done:
            await self.init_db()
        
        return list(self.ignored_users.get(chat_id, set()))


# 全局实例
group_admin = GroupAdmin()


