#!/usr/bin/env python3
"""离线冒烟：群管命令依赖的导入与核心逻辑（不连 Telegram）。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> int:
    errors: list[str] = []
    ok: list[str] = []

    def check(name: str, fn):
        try:
            fn()
            ok.append(name)
        except Exception as e:
            errors.append(f"{name}: {e}")

    # 导入
    check("import get_detector", lambda: __import__("services.group_admin.bayes_spam", fromlist=["get_detector"]).get_detector)
    check("import spam_log", lambda: __import__("services.group_admin.bayes_spam.spam_log", fromlist=["spam_log"]))
    check("GROUP_ADMIN_HELP_HTML", lambda: __import__("config.group_admin_help", fromlist=["GROUP_ADMIN_HELP_HTML"]).GROUP_ADMIN_HELP_HTML[:50])

    from services.group_admin import group_admin
    from services.group_admin.bayes_spam import get_detector, spam_log
    from services import telegram_moderation as mod

    await group_admin.init_db()

    chat_id = -1009990001
    user_id = 90001

    await group_admin.train_bayes_spam("离线测试广告加微信刷单", chat_id=chat_id)
    ok.append("train_bayes_spam")

    p = await group_admin.check_bayes_spam(chat_id, "加微信刷单日赚")
    if p is None:
        errors.append("check_bayes_spam: 期望命中未命中")
    else:
        ok.append(f"check_bayes_spam p={p:.2f}")

    await group_admin.train_bayes_ham("好的谢谢", chat_id=chat_id)
    ok.append("train_bayes_ham")

    log_id = await spam_log.log_detection(
        chat_id=chat_id,
        message_text="测试广告记录",
        p_spam=0.99,
        user_id=user_id,
        username="tester",
    )
    ok.append(f"spam_log.log_detection id={log_id}")

    entries = await spam_log.list_recent(chat_id, limit=5)
    if not entries:
        errors.append("list_recent: 空列表")
    else:
        ok.append(f"list_recent count={len(entries)}")

    text = await spam_log.mark_log_as_ham(entries[0].id, chat_id)
    if not text:
        errors.append("mark_log_as_ham: 失败")
    else:
        ok.append("mark_log_as_ham")

    banned = await group_admin.list_banned_users(chat_id)
    ok.append(f"list_banned_users count={len(banned)}")

    stats = await group_admin.get_violation_stats(chat_id, 7)
    ok.append(f"get_violation_stats total={stats.get('total', 0)}")

    v = await mod.check_text_violation(chat_id, "加微信刷单")
    ok.append(f"check_text_violation -> {v}")

    # handler 模块加载
    check("handlers.admin", lambda: __import__("handlers.admin"))
    check("handlers.commands", lambda: __import__("handlers.commands"))

    print("=== OK ===")
    for line in ok:
        print(" ", line)
    if errors:
        print("=== FAIL ===")
        for line in errors:
            print(" ", line)
        return 1
    print(f"\n共 {len(ok)} 项通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
