"""群管执法端口（领域/应用层仅依赖此接口）。"""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from services.ports.moderation_context import ModerationToolContext


class ModerationPort(Protocol):
    async def get_group_capabilities(self, chat_id: int) -> Dict[str, Any]: ...

    async def get_group_context_text(
        self,
        chat_id: int,
        *,
        requester_user_id: int,
        reply_message_id: Optional[int],
        reply_author_user_id: Optional[int],
    ) -> str: ...

    async def check_text_violation(self, chat_id: int, text: str) -> Optional[str]: ...

    async def execute_moderation(
        self,
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
    ) -> Dict[str, Any]: ...

    async def is_user_group_admin(self, chat_id: int, user_id: int) -> bool: ...


class TelegramModerationPort:
    """基于 services.telegram_moderation 的默认实现。"""

    async def get_group_capabilities(self, chat_id: int) -> Dict[str, Any]:
        from services import telegram_moderation as mod

        return await mod.get_group_capabilities(chat_id)

    async def get_group_context_text(
        self,
        chat_id: int,
        *,
        requester_user_id: int,
        reply_message_id: Optional[int],
        reply_author_user_id: Optional[int],
    ) -> str:
        from services import telegram_moderation as mod

        return await mod.get_group_context_text(
            chat_id,
            requester_user_id=requester_user_id,
            reply_message_id=reply_message_id,
            reply_author_user_id=reply_author_user_id,
        )

    async def check_text_violation(self, chat_id: int, text: str) -> Optional[str]:
        from services import telegram_moderation as mod

        return await mod.check_text_violation(chat_id, text)

    async def execute_moderation(
        self,
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
        from services import telegram_moderation as mod

        return await mod.execute_moderation(
            chat_id,
            action,
            target_user_id,
            message_id=message_id,
            hours=hours,
            reason=reason,
            operator_user_id=operator_user_id,
            require_operator_admin=require_operator_admin,
            allow_if_target_text_is_spam=allow_if_target_text_is_spam,
            target_message_text=target_message_text,
        )

    async def is_user_group_admin(self, chat_id: int, user_id: int) -> bool:
        from services import telegram_moderation as mod

        return await mod.is_user_group_admin(chat_id, user_id)


_default_port: Optional[TelegramModerationPort] = None


def get_moderation_port() -> ModerationPort:
    global _default_port
    if _default_port is None:
        _default_port = TelegramModerationPort()
    return _default_port
