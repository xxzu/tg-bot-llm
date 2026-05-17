"""群管持久化（SQLite 路径与表结构由 manager 初始化）。"""
from pathlib import Path

DB_FILE = Path(__file__).resolve().parents[2] / "data" / "group_admin.db"
