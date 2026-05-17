"""
通过 OpenRouter API 拉取可免费调用的聊天模型（prompt/completion 价格为 0）。
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_GENERATED_PATH = (
    Path(__file__).resolve().parents[1] / "models" / "openrouter_free_models.yaml"
)
_FILE_HEADER = (
    "# 由 scripts/sync_openrouter_free_models.py 自动生成，请勿手改。\n"
    "# 使用 OPENROUTER_API_KEY 调用 GET https://openrouter.ai/api/v1/models\n"
)


@dataclass(frozen=True)
class OpenRouterFreeModel:
    id: str
    name: str
    key: str
    display_name: str
    capabilities: tuple[str, ...]


def _pricing_is_free(pricing: Optional[Dict[str, Any]]) -> bool:
    if not pricing:
        return False
    for field in ("prompt", "completion"):
        raw = pricing.get(field)
        if raw is None:
            return False
        try:
            if float(raw) != 0.0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _is_chat_model(raw: Dict[str, Any]) -> bool:
    arch = raw.get("architecture") or {}
    out_mod = list(arch.get("output_modalities") or [])
    in_mod = list(arch.get("input_modalities") or [])
    if not out_mod:
        return True
    if out_mod == ["audio"]:
        return False
    if "text" not in out_mod:
        return False
    modality = str(arch.get("modality") or "")
    if "->image" in modality and "text" not in in_mod:
        return False
    return True


def model_id_to_key(model_id: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", model_id).strip("_").lower()
    if len(base) <= 48:
        return base
    digest = hashlib.sha256(model_id.encode()).hexdigest()[:8]
    return f"{base[:40]}_{digest}"


def _capabilities(raw: Dict[str, Any]) -> tuple[str, ...]:
    caps: List[str] = ["chat"]
    params = raw.get("supported_parameters") or []
    if "tools" in params:
        caps.append("tools")
    arch = raw.get("architecture") or {}
    in_mod = arch.get("input_modalities") or []
    # 仅当明确支持视觉理解时再标记（避免 Lyria 等音频模型误标）
    modality = str(arch.get("modality") or "")
    if "vision" in params or (
        "image" in in_mod and "text" in out_mod and "audio" not in out_mod
    ):
        if "audio" not in modality or "image" in modality:
            caps.append("vision")
    return tuple(caps)


def parse_free_chat_models(models: List[Dict[str, Any]]) -> List[OpenRouterFreeModel]:
    out: List[OpenRouterFreeModel] = []
    for raw in models:
        if not _pricing_is_free(raw.get("pricing")):
            continue
        if not _is_chat_model(raw):
            continue
        model_id = raw.get("id") or ""
        if not model_id:
            continue
        name = (raw.get("name") or model_id).strip()
        display = name
        if "(free)" not in display.lower():
            display = f"{display} (Free)" if len(display) < 48 else display
        out.append(
            OpenRouterFreeModel(
                id=model_id,
                name=name,
                key=model_id_to_key(model_id),
                display_name=display[:80],
                capabilities=_capabilities(raw),
            )
        )
    out.sort(key=lambda m: m.id)
    return out


async def fetch_openrouter_models(api_key: str) -> List[Dict[str, Any]]:
    import aiohttp

    if not api_key.strip():
        raise ValueError("OPENROUTER_API_KEY 未配置")

    headers = {"Authorization": f"Bearer {api_key.strip()}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            OPENROUTER_MODELS_URL,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=90),
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(
                    f"OpenRouter models API 失败: HTTP {resp.status} — {body[:500]}"
                )
            data = await resp.json(content_type=None)
    return list(data.get("data") or [])


def fetch_openrouter_models_sync(api_key: str) -> List[Dict[str, Any]]:
    import json
    import urllib.request

    if not api_key.strip():
        raise ValueError("OPENROUTER_API_KEY 未配置")
    req = urllib.request.Request(
        OPENROUTER_MODELS_URL,
        headers={"Authorization": f"Bearer {api_key.strip()}"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.load(resp)
    return list(data.get("data") or [])


def free_models_to_yaml_entries(models: List[OpenRouterFreeModel]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for m in models:
        label = m.display_name
        if len(label) > 42:
            label = label[:39] + "…"
        entries.append(
            {
                "id": m.id,
                "key": m.key,
                "provider": "openrouter",
                "menu": "openrouter",
                "display_name": m.display_name,
                "button_label": f"🆓 {label}",
                "capabilities": list(m.capabilities),
                "inference_profile": "openrouter_default",
            }
        )
    return entries


def write_openrouter_free_yaml(
    models: List[OpenRouterFreeModel],
    path: Path | None = None,
) -> Path:
    target = path or _GENERATED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"models": free_models_to_yaml_entries(models)}
    text = _FILE_HEADER + yaml.dump(
        payload,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    target.write_text(text, encoding="utf-8")
    return target


def sync_openrouter_free_models_sync(
    api_key: str,
    *,
    path: Path | None = None,
) -> tuple[Path, int]:
    raw = fetch_openrouter_models_sync(api_key)
    free = parse_free_chat_models(raw)
    out_path = write_openrouter_free_yaml(free, path=path)
    logger.info("已写入 %s 个免费 OpenRouter 模型到 %s", len(free), out_path)
    return out_path, len(free)


async def sync_openrouter_free_models(
    api_key: str,
    *,
    path: Path | None = None,
) -> tuple[Path, int]:
    raw = await fetch_openrouter_models(api_key)
    free = parse_free_chat_models(raw)
    out_path = write_openrouter_free_yaml(free, path=path)
    logger.info("已写入 %s 个免费 OpenRouter 模型到 %s", len(free), out_path)
    return out_path, len(free)
