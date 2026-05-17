"""贝叶斯广告模型独立数据库路径。"""
from pathlib import Path

BAYES_DB_FILE = Path(__file__).resolve().parents[3] / "data" / "bayes_spam.db"
