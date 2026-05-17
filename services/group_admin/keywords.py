"""违规关键词与文本匹配策略（无 Telegram / DB 依赖）。"""
from __future__ import annotations

from typing import Optional, Set

SCAM_KEYWORDS = [
    "刷单", "刷信誉", "兼职刷单", "日赚", "月入", "轻松赚钱",
    "投资理财", "高收益", "稳赚不赔", "包赚", "零风险",
    "加微信", "加QQ", "扫码", "点击链接", "领取红包",
    "中奖", "恭喜您", "免费领取", "限时优惠", "最后机会",
    "贷款", "放贷", "无抵押", "秒到账", "低利息",
    "代购", "海外代购", "免税", "正品保证",
    "赌博", "博彩", "彩票", "投注", "下注",
    "传销", "直销", "代理", "加盟", "发展下线",
    "刷单平台", "刷单群", "刷单软件",
]

PORNO_KEYWORDS = [
    "色情", "黄色", "成人", "18禁", "AV", "小电影",
    "约炮", "一夜情", "性服务", "上门服务",
    "裸聊", "视频聊天", "私密", "特殊服务",
    "包养", "援交", "外围", "模特", "陪游",
]

SPAM_KEYWORDS = [
    "广告", "推广", "营销", "代理", "招商",
    "加群", "进群", "拉群", "微信群", "QQ群",
    "转发", "分享", "点赞", "关注", "订阅",
]

ALL_BANNED_KEYWORDS = SCAM_KEYWORDS + PORNO_KEYWORDS + SPAM_KEYWORDS

_SCAM_SET = {kw.lower() for kw in SCAM_KEYWORDS}
_PORNO_SET = {kw.lower() for kw in PORNO_KEYWORDS}
_SPAM_SET = {kw.lower() for kw in SPAM_KEYWORDS}


def default_keyword_set() -> Set[str]:
    return {kw.lower() for kw in ALL_BANNED_KEYWORDS}


def classify_keyword(keyword: str) -> str:
    if keyword in _SCAM_SET:
        return "scam"
    if keyword in _PORNO_SET:
        return "porno"
    if keyword in _SPAM_SET:
        return "spam"
    return "spam"


def match_violation(text: str, effective_keywords: Set[str]) -> Optional[str]:
    if not text:
        return None
    text_lower = text.lower()
    for keyword in effective_keywords:
        if keyword in text_lower:
            return classify_keyword(keyword)
    return None
