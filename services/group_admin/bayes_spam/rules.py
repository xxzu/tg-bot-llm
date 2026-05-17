"""规则预检（参考 bayes_spam_sniper RuleBasedClassifier）。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class RuleResult:
    is_spam: bool
    reason: str = ""


def check_chinese_spacing_spam(
    text: str,
    *,
    ratio_threshold: float = 0.8,
    min_chinese_chars: int = 5,
) -> RuleResult:
    """汉字间故意加空格规避关键词（如「跟 单 像 捡 钱」）。"""
    if not text or not re.search(r"[\u4e00-\u9fff]", text):
        return RuleResult(False)
    spaced = len(re.findall(r"[\u4e00-\u9fff](?=\s)", text))
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    if chinese < min_chinese_chars:
        return RuleResult(False)
    ratio = spaced / chinese if chinese else 0.0
    if ratio > ratio_threshold:
        return RuleResult(True, f"chinese_spacing_ratio={ratio:.2f}")
    return RuleResult(False)
