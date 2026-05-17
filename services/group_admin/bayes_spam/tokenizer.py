"""分词：中文 jieba + 英文/数字/表情（参考 bayes_spam_sniper tokenize）。"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import List

from services.group_admin.bayes_spam.cleaner import clean_text

_EMOJI = re.compile(
    r"([\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F600-\U0001F64F]+)"
)
_PUNCT_CHARS = "。、，！？；：""''（）【】《》…—–!?.,;:'\"()[]{}"
_TOKEN_RE = re.compile(
    r"(__[A-Z_]+__)|"
    r"([\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F600-\U0001F64F]+)|"
    r"([\u4e00-\u9fff]+)|"
    r"([a-zA-Z0-9]+)|"
    rf"([{re.escape(_PUNCT_CHARS)}]+)"
)
_PUNCT_ONLY = re.compile(rf"^[{re.escape(_PUNCT_CHARS)}]+$")
_NUM_ONLY = re.compile(r"^[0-9一二三四五六七八九十百千万亿零]+$")


@lru_cache(maxsize=1)
def _jieba_cut(text: str) -> tuple:
    try:
        import jieba

        return tuple(jieba.cut(text, cut_all=False))
    except ImportError:
        return tuple(text)


def tokenize(text: str) -> List[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []

    parts: List[str] = []
    for m in _TOKEN_RE.finditer(cleaned):
        parts.append(next(g for g in m.groups() if g))

    out: List[str] = []
    for token in parts:
        if not token or not token.strip():
            continue
        if _EMOJI.fullmatch(token):
            out.extend(list(token))
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            out.extend(_jieba_cut(token))
            continue
        if _PUNCT_ONLY.match(token) or _NUM_ONLY.match(token):
            continue
        out.append(token.lower())
    return [t for t in out if t]
