#!/usr/bin/env python3
"""
喵喵 Telegram 群管 MCP Server（stdio）

在 Cursor / Claude Desktop 等客户端的配置中注册，例如：
{
  "mcpServers": {
    "miaomiao-telegram-mod": {
      "command": "/root/tg_bot/gemini_tg_bot/.venv/bin/python",
      "args": ["/root/tg_bot/gemini_tg_bot/mcp_server/server.py"],
      "cwd": "/root/tg_bot/gemini_tg_bot",
      "env": {
        "TG_BOT_TOKEN": "你的token"
      }
    }
  }
}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    raise SystemExit(
        "缺少 mcp 包，请执行: pip install 'mcp>=1.2.0'\n" + str(e)
    ) from e

from services import telegram_moderation as mod

mcp = FastMCP(
    "miaomiao-telegram-moderation",
    instructions=(
        "喵喵 Telegram 机器人群管工具。"
        "所有写操作需要 chat_id；处置某条消息时需 target_user_id 与 message_id。"
        "建议先调用 miaomiao_group_capabilities 确认权限。"
    ),
)


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
async def miaomiao_group_capabilities(chat_id: int) -> str:
    """查询喵喵在指定群的管理员身份与 Telegram 权限（删消息/禁言/封禁等）。"""
    caps = await mod.get_group_capabilities(chat_id)
    return _json(caps)


@mcp.tool()
async def miaomiao_group_context(
    chat_id: int,
    requester_user_id: int = 0,
    reply_message_id: int = 0,
    reply_author_user_id: int = 0,
) -> str:
    """获取群环境与执法能力的中文说明，供模型理解当前上下文。"""
    return await mod.get_group_context_text(
        chat_id,
        requester_user_id=requester_user_id or None,
        reply_message_id=reply_message_id or None,
        reply_author_user_id=reply_author_user_id or None,
    )


@mcp.tool()
async def miaomiao_check_message(chat_id: int, text: str) -> str:
    """检查文本是否命中群内屏蔽词（广告/诈骗/色情/垃圾），返回 violation_type 或 null。"""
    v = await mod.check_text_violation(chat_id, text)
    return _json({"violation_type": v, "is_violation": v is not None})


@mcp.tool()
async def miaomiao_moderate(
    chat_id: int,
    action: str,
    target_user_id: int,
    message_id: int = 0,
    hours: int = 24,
    reason: str = "",
    operator_user_id: int = 0,
    require_operator_admin: bool = True,
) -> str:
    """
    执行群管动作。action: mute | ban | kick | warn | del | unban。
    del 需 message_id；mute 用 hours(1-168)。operator_user_id 为发令者 Telegram user_id。
    """
    target_text = None
    result = await mod.execute_moderation(
        chat_id,
        action,
        target_user_id,
        message_id=message_id or None,
        hours=hours,
        reason=reason,
        operator_user_id=operator_user_id,
        require_operator_admin=require_operator_admin,
        allow_if_target_text_is_spam=False,
        target_message_text=target_text,
    )
    return _json(result)


@mcp.tool()
async def miaomiao_moderate_spam(
    chat_id: int,
    target_user_id: int,
    message_id: int,
    message_text: str,
    action: str = "mute",
    hours: int = 24,
    reason: str = "广告/垃圾信息",
) -> str:
    """
    当 message_text 命中屏蔽词时执行处置（可不校验 operator 为群管）。
    典型：先 miaomiao_check_message，再对本工具传入同一正文。
    """
    v = await mod.check_text_violation(chat_id, message_text)
    if v is None:
        return _json({"ok": False, "message": "文本未命中屏蔽词，拒绝自动执法"})
    result = await mod.execute_moderation(
        chat_id,
        action,
        target_user_id,
        message_id=message_id,
        hours=hours,
        reason=reason or v,
        operator_user_id=0,
        require_operator_admin=False,
        allow_if_target_text_is_spam=True,
        target_message_text=message_text,
    )
    result["violation_type"] = v
    return _json(result)


@mcp.tool()
async def miaomiao_keyword_add(chat_id: int, keyword: str) -> str:
    """为群添加自定义屏蔽词。"""
    ok = await mod.add_keyword(chat_id, keyword)
    return _json({"ok": ok, "keyword": keyword})


@mcp.tool()
async def miaomiao_keyword_list(chat_id: int) -> str:
    """列出群自定义屏蔽词（不含全局内置词）。"""
    kws = await mod.list_keywords(chat_id)
    return _json({"keywords": kws})


@mcp.tool()
async def miaomiao_violation_stats(chat_id: int, days: int = 7) -> str:
    """查询近期违规统计。"""
    stats = await mod.get_violation_stats(chat_id, days)
    return _json(stats)


if __name__ == "__main__":
    mcp.run(transport="stdio")
