"""贝叶斯广告识别（思路参考 bayes_spam_sniper / Paul Graham spam filter）。"""
from services.group_admin.bayes_spam.detector import (
    BayesSpamDetector,
    ClassificationResult,
    get_detector,
)

__all__ = ["BayesSpamDetector", "ClassificationResult", "get_detector"]
