"""Telegram 群管理员权限字段（兼容 aiogram 新旧 Bot API 字段名）。"""
from __future__ import annotations

from aiogram.types import ChatMemberAdministrator


def admin_has_perm(member: ChatMemberAdministrator, *names: str) -> bool:
    for name in names:
        if getattr(member, name, False):
            return True
    return False


def collect_admin_permissions(member: ChatMemberAdministrator) -> list[str]:
    """返回标准化权限标签列表。"""
    perms: list[str] = []
    if admin_has_perm(member, "can_delete_messages"):
        perms.append("delete_messages")
    if admin_has_perm(member, "can_restrict_members", "can_ban_users"):
        perms.append("restrict_members")
        perms.append("ban_users")
    if admin_has_perm(member, "can_pin_messages"):
        perms.append("pin_messages")
    if admin_has_perm(member, "can_manage_chat"):
        perms.append("manage_chat")
    return perms
