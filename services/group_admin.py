"""
群组管理模块
提供关键词过滤、用户管理、自动删除违规消息等功能
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import List, Set, Optional, Dict
from pathlib import Path

import aiosqlite
from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner, ChatPermissions

# 不再使用连接池，直接使用 aiosqlite.connect()

logger = logging.getLogger(__name__)

# 数据库文件路径
DB_FILE = Path(__file__).parent.parent / "data" / "group_admin.db"

# 违规关键词列表（可以扩展）
SCAM_KEYWORDS = [
    # 诈骗相关
    "刷单", "刷信誉", "兼职刷单", "日赚", "月入", "轻松赚钱",
    "投资理财", "高收益", "稳赚不赔", "包赚", "零风险",
    "加微信", "加QQ", "扫码", "点击链接", "领取红包",
    "中奖", "恭喜您", "免费领取", "限时优惠", "最后机会",
    "贷款", "放贷", "无抵押", "秒到账", "低利息",
    "代购", "海外代购", "免税", "正品保证",
    "赌博", "博彩", "彩票", "投注", "下注",
    "传销", "直销", "代理", "加盟", "发展下线",
    "刷单平台", "刷单群", "刷单软件",
]

PORNO_KEYWORDS = [
    # 色情相关
    "色情", "黄色", "成人", "18禁", "AV", "小电影",
    "约炮", "一夜情", "性服务", "上门服务",
    "裸聊", "视频聊天", "私密", "特殊服务",
    "包养", "援交", "外围", "模特", "陪游",
]

SPAM_KEYWORDS = [
    # 垃圾信息
    "广告", "推广", "营销", "代理", "招商",
    "加群", "进群", "拉群", "微信群", "QQ群",
    "转发", "分享", "点赞", "关注", "订阅",
]

# 合并所有关键词
ALL_BANNED_KEYWORDS = SCAM_KEYWORDS + PORNO_KEYWORDS + SPAM_KEYWORDS


class GroupAdmin:
    """群组管理类"""
    
    def __init__(self):
        # 默认内置关键词（全局）
        self.default_banned_keywords: Set[str] = {kw.lower() for kw in ALL_BANNED_KEYWORDS}
        # 每个 chat 的自定义关键词（仅存自定义部分；默认关键词始终生效）
        self.chat_banned_keywords: Dict[int, Set[str]] = {}
        self.user_warnings: Dict[int, int] = {}  # {user_id: warning_count}
        self.user_bans: Set[int] = set()  # 被封禁的用户ID
        # 每个 chat 的被忽略用户集合 {chat_id: {user_id, ...}}
        self.ignored_users: Dict[int, Set[int]] = {}
        self.async_init_done = False
    
    async def init_db(self):
        """初始化数据库"""
        if self.async_init_done:
            return
        
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
        
        # 加载已封禁用户
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute("SELECT user_id FROM banned_users WHERE unbanned_at IS NULL") as cursor:
                rows = await cursor.fetchall()
                self.user_bans = {row[0] for row in rows}

        # 加载自定义屏蔽词（按 chat 聚合到内存缓存）
        async with aiosqlite.connect(DB_FILE) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            async with conn.execute("SELECT chat_id, keyword FROM chat_banned_keywords") as cursor:
                rows = await cursor.fetchall()
                chat_map: Dict[int, Set[str]] = {}
                for chat_id, keyword in rows:
                    if not keyword:
                        continue
                    chat_map.setdefault(int(chat_id), set()).add(str(keyword).lower())
                self.chat_banned_keywords = chat_map
        
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
    
    def _get_effective_keywords(self, chat_id: int) -> Set[str]:
        """获取某个 chat 下生效的关键词集合（默认 + 自定义）"""
        custom = self.chat_banned_keywords.get(chat_id, set())
        # default 永远生效，自定义叠加
        return self.default_banned_keywords | custom

    def check_keywords(self, chat_id: int, text: str) -> Optional[str]:
        """检查文本是否包含违规关键词（按 chat 生效）"""
        if not text:
            return None
        
        text_lower = text.lower()
        effective_keywords = self._get_effective_keywords(chat_id)
        for keyword in effective_keywords:
            if keyword in text_lower:
                # 判断关键词类型
                # 仅对默认关键词做类型分类；自定义关键词统一按 spam 处理
                if keyword in {kw.lower() for kw in SCAM_KEYWORDS}:
                    return "scam"
                elif keyword in {kw.lower() for kw in PORNO_KEYWORDS}:
                    return "porno"
                elif keyword in {kw.lower() for kw in SPAM_KEYWORDS}:
                    return "spam"
                else:
                    return "spam"
        
        return None
    
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
            
            self.user_bans.add(user_id)
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
            
            self.user_bans.discard(user_id)
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
    
    async def handle_violation(
        self, 
        bot: Bot, 
        message: types.Message, 
        violation_type: str
    ) -> bool:
        """处理违规消息"""
        chat_id = message.chat.id
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name
        message_text = message.text or message.caption or ""
        
        # 检查用户是否已被封禁
        if user_id in self.user_bans:
            await self.delete_message(bot, chat_id, message.message_id)
            return True
        
        # 删除违规消息
        deleted = await self.delete_message(bot, chat_id, message.message_id)
        
        if not deleted:
            return False
        
        # 记录违规行为
        await self.record_violation(
            chat_id, user_id, username, message_text, 
            violation_type, "消息已删除"
        )
        
        # 根据违规类型采取不同措施
        if violation_type == "scam":
            # 诈骗消息：警告并可能封禁
            warning_count = await self.warn_user(bot, chat_id, user_id, "发送诈骗信息")
            if warning_count >= 3:
                await self.ban_user(bot, chat_id, user_id, "多次发送诈骗信息", banned_by=bot.id)
                await bot.send_message(
                    chat_id, 
                    f"⚠️ 用户 @{username} 因多次违规已被封禁"
                )
            else:
                await bot.send_message(
                    chat_id,
                    f"⚠️ 检测到违规内容，已删除。用户 @{username} 警告 {warning_count}/3"
                )
        
        elif violation_type == "porno":
            # 色情内容：直接封禁
            await self.ban_user(bot, chat_id, user_id, "发送色情内容", banned_by=bot.id)
            await bot.send_message(
                chat_id,
                f"🚫 用户 @{username} 因发送色情内容已被封禁"
            )
        
        elif violation_type == "spam":
            from config.performance import SPAM_AUTO_MUTE_HOURS

            warning_count = await self.warn_user(bot, chat_id, user_id, "发送垃圾/广告信息")
            mute_note = ""
            if SPAM_AUTO_MUTE_HOURS > 0:
                until = datetime.now() + timedelta(hours=SPAM_AUTO_MUTE_HOURS)
                if await self.mute_user(bot, chat_id, user_id, until):
                    mute_note = f"，已禁言 {SPAM_AUTO_MUTE_HOURS} 小时"

            if warning_count >= 5:
                await self.ban_user(bot, chat_id, user_id, "多次发送垃圾信息", banned_by=bot.id)
                await bot.send_message(
                    chat_id,
                    f"⚠️ 用户 @{username} 因多次发送垃圾信息已被封禁",
                )
            else:
                await bot.send_message(
                    chat_id,
                    f"⚠️ 检测到广告/垃圾信息，已删除。用户 @{username} 警告 {warning_count}/5{mute_note}",
                )
        
        return True
    
    async def check_and_handle_message(self, bot: Bot, message: types.Message) -> bool:
        """检查消息并处理违规内容"""
        # 群组/频道内工作（频道需要机器人在频道里有相应权限才能收到消息）
        if message.chat.type not in ["group", "supergroup", "channel"]:
            return False
        
        # 检查消息文本
        message_text = message.text or message.caption or ""
        if not message_text:
            return False
        
        # 检查关键词
        violation_type = self.check_keywords(message.chat.id, message_text)
        if violation_type:
            await self.handle_violation(bot, message, violation_type)
            return True
        
        return False
    
    async def add_keyword(self, chat_id: int, keyword: str) -> bool:
        """添加自定义关键词到某个 chat 的黑名单（持久化），返回是否新增成功"""
        kw = (keyword or "").strip().lower()
        if not kw:
            return False

        # 初始化数据库
        if not self.async_init_done:
            await self.init_db()

        try:
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                cursor = await conn.execute(
                    "INSERT OR IGNORE INTO chat_banned_keywords (chat_id, keyword) VALUES (?, ?)",
                    (chat_id, kw),
                )
                await conn.commit()

            # 更新内存缓存
            self.chat_banned_keywords.setdefault(chat_id, set()).add(kw)
            added = (cursor.rowcount or 0) > 0
            logger.info(f"chat_id={chat_id} 已添加自定义关键词: {kw} (added={added})")
            return added
        except Exception as e:
            logger.error(f"添加自定义关键词失败 chat_id={chat_id}, keyword={kw}: {e}")
            return False
    
    async def remove_keyword(self, chat_id: int, keyword: str) -> bool:
        """从某个 chat 的自定义黑名单移除关键词（持久化），返回是否删除成功"""
        kw = (keyword or "").strip().lower()
        if not kw:
            return False

        if not self.async_init_done:
            await self.init_db()

        try:
            async with aiosqlite.connect(DB_FILE) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                cursor = await conn.execute(
                    "DELETE FROM chat_banned_keywords WHERE chat_id = ? AND keyword = ?",
                    (chat_id, kw),
                )
                await conn.commit()

            # 更新内存缓存
            if chat_id in self.chat_banned_keywords:
                self.chat_banned_keywords[chat_id].discard(kw)
                if not self.chat_banned_keywords[chat_id]:
                    self.chat_banned_keywords.pop(chat_id, None)

            removed = (cursor.rowcount or 0) > 0
            logger.info(f"chat_id={chat_id} 已移除自定义关键词: {kw} (removed={removed})")
            return removed
        except Exception as e:
            logger.error(f"移除自定义关键词失败 chat_id={chat_id}, keyword={kw}: {e}")
            return False

    async def list_keywords(self, chat_id: int) -> List[str]:
        """列出某个 chat 的自定义关键词（不含默认关键词），按字母排序"""
        if not self.async_init_done:
            await self.init_db()

        # 优先从内存缓存取（保证增删后立刻可见）
        kws = sorted(self.chat_banned_keywords.get(chat_id, set()))
        return kws
    
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


