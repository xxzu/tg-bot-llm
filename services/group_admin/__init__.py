"""群组管理包：对外仍导出 group_admin 单例。"""
from services.group_admin.manager import GroupAdmin, group_admin

__all__ = ["GroupAdmin", "group_admin"]
