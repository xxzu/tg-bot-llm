"""
群管 OpenAI-style function calling 工具定义与执行（与 MCP / telegram_moderation 共用）。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from services.ports.moderation_context import ModerationToolContext
from services.ports.moderation_port import ModerationPort, get_moderation_port

logger = logging.getLogger(__name__)

# 兼容旧 import 路径
__all__ = [
    "OPENAI_MODERATION_TOOLS",
    "ModerationToolContext",
    "build_tools_system_addon",
    "execute_tool",
    "should_use_group_tools",
]

OPENAI_MODERATION_TOOLS: List[dict] = [
    {
        "type": "function",
        "function": {
            "name": "check_message_violation",
            "description": (
                "贝叶斯检查文本是否为广告/垃圾。"
                "处置前先检查被引用消息正文。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "待检查文本"}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "telegram_moderate",
            "description": (
                "对当前会话上下文中「用户引用的那条消息」的作者执行群管。"
                "无引用消息时不可调用。不要对群管理员或其他机器人调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["mute", "ban", "kick", "warn", "del"],
                    },
                    "reason": {"type": "string"},
                    "hours": {"type": "integer"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_group_moderation_status",
            "description": "查询喵喵在本群的管理员权限与是否可执法",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def build_tools_system_addon(ctx: ModerationToolContext) -> str:
    if not ctx.can_moderate:
        return (
            "【群管工具】你在本群无执法权限，不要调用 telegram_moderate。"
            "可提示群管理员为喵喵开启删消息/禁言/封禁权限。"
        )
    lines = [
        "【群管工具】你已接入 Telegram 群管 function calling，请用工具执法，不要输出 @@MOD 标记。",
        f"chat_id={ctx.chat_id}，操作者 user_id={ctx.operator_user_id}，"
        f"是否群管={'是' if ctx.requester_is_admin else '否'}。",
    ]
    if ctx.reply_message_id and ctx.reply_target_user_id:
        lines.append(
            f"用户引用了 message_id={ctx.reply_message_id}，作者 user_id={ctx.reply_target_user_id}。"
        )
        if ctx.reply_text:
            lines.append(f"引用正文摘要: {ctx.reply_text[:500]}")
    else:
        lines.append("当前无引用消息：仅可闲聊或建议管理员「回复违规消息后再 @ 你」。")
    lines.append(
        "流程建议：明显广告/垃圾时先 check_message_violation(引用正文)，"
        "再 telegram_moderate；处置后用 1～3 句中文向群里说明，勿暴露工具名。"
    )
    if not ctx.requester_is_admin:
        lines.append("操作者非群管：仅当 check 命中违规类型时才可 telegram_moderate。")
    return "\n".join(lines)


async def execute_tool(
    name: str,
    arguments: Any,
    ctx: ModerationToolContext,
    port: Optional[ModerationPort] = None,
) -> str:
    port = port or get_moderation_port()
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}

    try:
        if name == "get_group_moderation_status":
            caps = await port.get_group_capabilities(ctx.chat_id)
            text = await port.get_group_context_text(
                ctx.chat_id,
                requester_user_id=ctx.operator_user_id,
                reply_message_id=ctx.reply_message_id,
                reply_author_user_id=ctx.reply_target_user_id,
            )
            return json.dumps({"capabilities": caps, "summary": text}, ensure_ascii=False)

        if name == "check_message_violation":
            text = str(arguments.get("text") or ctx.reply_text or "")
            v = await port.check_text_violation(ctx.chat_id, text)
            return json.dumps(
                {
                    "violation_type": v,
                    "is_violation": v is not None,
                    "text_preview": text[:200],
                },
                ensure_ascii=False,
            )

        if name == "telegram_moderate":
            if not ctx.reply_target_user_id:
                return json.dumps(
                    {"ok": False, "message": "无引用消息，无法确定处置对象"},
                    ensure_ascii=False,
                )
            action = str(arguments.get("action", "")).lower()
            hours = int(arguments.get("hours") or 24)
            reason = str(arguments.get("reason") or "违规")
            quoted_is_ad = False
            if ctx.reply_text:
                quoted_is_ad = (
                    await port.check_text_violation(ctx.chat_id, ctx.reply_text) is not None
                )
            out = await port.execute_moderation(
                ctx.chat_id,
                action,
                ctx.reply_target_user_id,
                message_id=ctx.reply_message_id if action == "del" else None,
                hours=hours,
                reason=reason,
                operator_user_id=ctx.operator_user_id,
                require_operator_admin=True,
                allow_if_target_text_is_spam=quoted_is_ad,
                target_message_text=ctx.reply_text,
            )
            return json.dumps(out, ensure_ascii=False)

        return json.dumps({"ok": False, "message": f"未知工具: {name}"}, ensure_ascii=False)
    except Exception as e:
        logger.exception("tool 执行失败 %s", name)
        return json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False)


def should_use_group_tools(chat_type: str, model_spec) -> bool:
    from config.performance import GROUP_MOD_TOOLS_ENABLED

    if not GROUP_MOD_TOOLS_ENABLED:
        return False
    if chat_type not in ("group", "supergroup"):
        return False
    if model_spec is None:
        return False
    return model_spec.supports("tools")
