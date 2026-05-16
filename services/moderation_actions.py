"""
解析模型回复中的 @@MOD:...@@ 指令并调用 group_admin 执行。
"""
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from aiogram import Bot
from aiogram.types import Message

from services import telegram_moderation as mod
from services.group_admin import group_admin

logger = logging.getLogger(__name__)

MOD_PATTERN = re.compile(
    r"@@MOD:(mute|ban|kick|warn|del)(?:\|([^@]*?))?@@",
    re.IGNORECASE,
)


@dataclass
class ModAction:
    action: str
    arg: str = ""


def parse_and_strip_mod_tags(text: str) -> Tuple[str, List[ModAction]]:
    actions: List[ModAction] = []
    for m in MOD_PATTERN.finditer(text or ""):
        actions.append(ModAction(action=m.group(1).lower(), arg=(m.group(2) or "").strip()))
    clean = MOD_PATTERN.sub("", text or "").strip()
    return clean, actions


async def apply_moderation_actions(
    bot: Bot,
    message: Message,
    actions: List[ModAction],
    *,
    requester_is_admin: bool,
) -> List[str]:
    """
    执行 MOD 指令。返回已执行操作的简短说明（可追加到群通知）。
    """
    if not actions or message.chat.type not in ("group", "supergroup"):
        return []

    chat_id = message.chat.id
    caps = await mod.get_group_capabilities(chat_id)
    if not caps.get("can_moderate"):
        return []

    reply = message.reply_to_message
    if not reply or not reply.from_user:
        return []

    target = reply.from_user
    if target.is_bot:
        return []

    quoted_body = (reply.text or reply.caption or "").strip()
    quoted_is_ad = group_admin.check_keywords(chat_id, quoted_body) is not None

    results: List[str] = []
    operator_id = message.from_user.id if message.from_user else 0

    for act in actions:
        if not requester_is_admin and not quoted_is_ad:
            continue

        hours = 24
        reason = act.arg or ""
        if act.action == "mute" and act.arg:
            parts = act.arg.split("|")
            try:
                hours = int(parts[0])
            except ValueError:
                pass
            if len(parts) > 1:
                reason = parts[1]

        try:
            out = await mod.execute_moderation(
                chat_id,
                act.action,
                target.id,
                message_id=reply.message_id if act.action == "del" else None,
                hours=hours,
                reason=reason or "违规",
                operator_user_id=operator_id,
                require_operator_admin=True,
                allow_if_target_text_is_spam=quoted_is_ad,
                target_message_text=quoted_body if quoted_is_ad else None,
            )
            if out.get("ok"):
                results.append(out.get("message") or act.action)
            elif out.get("message"):
                results.append(out["message"])
        except Exception as e:
            logger.exception("执行 MOD 失败: %s", act)
            results.append(f"{act.action}失败")

    return results
