"""
群聊图片视觉审核：调用 VL 模型 → 解析 JSON → 删消息/警告/封禁 + 群内简短说明。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from aiogram import Bot
from aiogram.types import Message

from config.group_image_moderation import (
    GROUP_IMAGE_MODERATION_PROMPT,
    GROUP_IMAGE_MOD_ENABLED,
    GROUP_IMAGE_SCAM_WARN_BAN,
    GROUP_IMAGE_VIOLATION_CONFIDENCE,
)
from services.gemini import download_and_encode_image
from services.group_admin import group_admin
from services.llm import get_invoker
from services.llm.registry import resolve_vision_model_id
from services.llm.types import LLMVisionRequest

logger = logging.getLogger(__name__)


@dataclass
class GroupImageModerationOutcome:
    checked: bool = False
    violation: bool = False
    violation_type: str = "none"
    brief_notice: str = ""
    error: str = ""


def _build_prompt(caption: str) -> str:
    cap = (caption or "").strip() or "（无）"
    return GROUP_IMAGE_MODERATION_PROMPT.format(caption=cap)


def _parse_vision_json(raw: str) -> Optional[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


async def moderate_group_photo(
    bot: Bot,
    message: Message,
) -> GroupImageModerationOutcome:
    """对群聊图片做视觉审核；无违规时 brief_notice 为空。"""
    if not GROUP_IMAGE_MOD_ENABLED:
        return GroupImageModerationOutcome(checked=False)

    if message.chat.type not in ("group", "supergroup"):
        return GroupImageModerationOutcome(checked=False)

    user = message.from_user
    if not user or group_admin.is_ignored(message.chat.id, user.id):
        return GroupImageModerationOutcome(checked=False)

    if not group_admin.async_init_done:
        await group_admin.init_db()

    from services import telegram_moderation as mod

    caps = await mod.get_group_capabilities(message.chat.id)
    if not caps.get("can_moderate"):
        return GroupImageModerationOutcome(
            checked=True,
            error=caps.get("error") or "喵喵无删消息/封禁权限，无法处置图片",
        )

    photo = message.photo[-1] if message.photo else None
    if not photo:
        return GroupImageModerationOutcome(checked=False)

    vision_model_id = resolve_vision_model_id("", purpose="group_moderation")
    if not vision_model_id:
        return GroupImageModerationOutcome(
            checked=True,
            error="未配置可用的视觉审核模型（GEMINI_API_KEY 或 OPENROUTER_API_KEY）",
        )

    file_info = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
    try:
        base64_image = await download_and_encode_image(file_url)
    except Exception as e:
        logger.exception("下载群聊图片失败")
        return GroupImageModerationOutcome(checked=True, error=str(e))

    caption = (message.caption or "").strip()
    invoker = get_invoker()
    try:
        raw = await invoker.vision(
            LLMVisionRequest(
                model_id=vision_model_id,
                prompt=_build_prompt(caption),
                image_base64=base64_image,
            )
        )
    except Exception as e:
        logger.exception("群聊图片视觉审核 API 失败")
        return GroupImageModerationOutcome(checked=True, error=str(e))

    parsed = _parse_vision_json(raw)
    if not parsed:
        logger.warning("群聊图片审核 JSON 解析失败: %s", raw[:300])
        return GroupImageModerationOutcome(checked=True, error="审核结果解析失败")

    violation = bool(parsed.get("violation"))
    vtype = str(parsed.get("type") or "none").lower().strip()
    try:
        confidence = float(parsed.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(parsed.get("reason") or "").strip()[:80]

    if not violation or confidence < GROUP_IMAGE_VIOLATION_CONFIDENCE:
        return GroupImageModerationOutcome(
            checked=True,
            violation=False,
            violation_type=vtype if violation else "none",
        )

    if vtype not in ("spam", "scam", "porno", "gambling", "other"):
        vtype = "spam" if vtype == "none" else "other"

    handled, notice = await group_admin.handle_vision_image_violation(
        bot,
        message,
        violation_type=vtype,
        reason=reason,
        confidence=confidence,
    )
    if not handled:
        return GroupImageModerationOutcome(
            checked=True,
            violation=True,
            violation_type=vtype,
            error="判定违规但处置失败（可能缺少删消息权限）",
        )

    return GroupImageModerationOutcome(
        checked=True,
        violation=True,
        violation_type=vtype,
        brief_notice=notice,
    )
