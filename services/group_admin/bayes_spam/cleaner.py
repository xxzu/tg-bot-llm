"""文本清洗（简化自 bayes_spam_sniper TextCleaner）。"""
from __future__ import annotations

import re

_HAN = r"\u4e00-\u9fff"
_SEP = re.compile(rf"([{_HAN}A-Za-z0-9])[^ {_HAN}A-Za-z0-9\s]+([{_HAN}A-Za-z0-9])")
_HAN_SPACE = re.compile(rf"([{_HAN}])(\s+)([{_HAN}])")
_MIXED = (
    (re.compile(rf"([{_HAN}])([A-Za-z0-9])"), r"\1 \2"),
    (re.compile(rf"([A-Za-z0-9])([{_HAN}])"), r"\1 \2"),
)


def clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned = str(text).strip()
    prev = ""
    while prev != cleaned:
        prev = cleaned
        cleaned = _SEP.sub(r"\1\2", cleaned)
    prev = ""
    while prev != cleaned:
        prev = cleaned
        cleaned = _HAN_SPACE.sub(r"\1\3", cleaned)
    for pat, repl in _MIXED:
        cleaned = pat.sub(repl, cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
