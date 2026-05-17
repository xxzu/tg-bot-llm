#!/usr/bin/env python3
"""
使用 OPENROUTER_API_KEY 从 OpenRouter 拉取所有可免费调用的聊天模型，
写入 models/openrouter_free_models.yaml，供 llm registry 合并加载。

用法（在 gemini_tg_bot 目录）:
  uv run python scripts/sync_openrouter_free_models.py
  uv run python scripts/sync_openrouter_free_models.py --list
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from services.llm.registry import reload_registry
from services.openrouter_catalog import (
    fetch_openrouter_models_sync,
    parse_free_chat_models,
    sync_openrouter_free_models_sync,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 OpenRouter 免费模型到 YAML")
    parser.add_argument(
        "--list",
        action="store_true",
        help="仅列出免费模型，不写文件",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="写入后刷新内存中的 registry 缓存（供脚本内验证）",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("错误: 请在 .env 中设置 OPENROUTER_API_KEY", file=sys.stderr)
        return 1

    if args.list:
        raw = fetch_openrouter_models_sync(api_key)
        free = parse_free_chat_models(raw)
        print(f"共 {len(free)} 个可免费调用的聊天模型:\n")
        for m in free:
            caps = ",".join(m.capabilities)
            print(f"  {m.id}\n    {m.display_name}  [{caps}]")
        return 0

    path, count = sync_openrouter_free_models_sync(api_key)
    print(f"已同步 {count} 个模型 -> {path}")

    if args.reload:
        reg = reload_registry()
        menu = reg.list_menu_models("openrouter")
        print(f"registry 中 openrouter 菜单项: {len(menu)} 个")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
