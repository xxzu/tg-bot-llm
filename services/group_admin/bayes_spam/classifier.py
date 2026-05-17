"""朴素贝叶斯分类器（对 port bayes_spam_sniper SpamClassifierService）。"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from services.group_admin.bayes_spam.tokenizer import tokenize


@dataclass
class ClassifierState:
    spam_counts: Dict[str, int] = field(default_factory=dict)
    ham_counts: Dict[str, int] = field(default_factory=dict)
    total_spam_words: int = 0
    total_ham_words: int = 0
    total_spam_messages: int = 0
    total_ham_messages: int = 0
    vocabulary_size: int = 0

    def vocabulary(self) -> Set[str]:
        return set(self.spam_counts) | set(self.ham_counts)


class NaiveBayesSpamClassifier:
    """Log-odds Naive Bayes，ham 样本双倍权重以降低误杀（Paul Graham bias）。"""

    def __init__(
        self,
        state: ClassifierState | None = None,
        *,
        probability_threshold: float = 0.94,
        short_message_word_threshold: int = 3,
        top_tokens: int = 15,
    ):
        self.state = state or ClassifierState()
        self.probability_threshold = probability_threshold
        self.short_message_word_threshold = short_message_word_threshold
        self.top_tokens = top_tokens
        self._vocab_cache: Set[str] | None = None

    def train(self, text: str, *, is_spam: bool) -> None:
        tokens = tokenize(text)
        if not tokens:
            return
        st = self.state
        if is_spam:
            st.total_spam_messages += 1
            st.total_spam_words += len(tokens)
            for tok in tokens:
                st.spam_counts[tok] = st.spam_counts.get(tok, 0) + 1
        else:
            st.total_ham_messages += 1
            st.total_ham_words += len(tokens) * 2
            for tok in tokens:
                st.ham_counts[tok] = st.ham_counts.get(tok, 0) + 2
        self._vocab_cache = None
        st.vocabulary_size = len(st.vocabulary())

    def classify(self, text: str) -> Tuple[bool, float]:
        st = self.state
        if st.total_ham_messages == 0 or st.total_spam_messages == 0:
            return False, 0.0

        total_messages = st.total_spam_messages + st.total_ham_messages
        if total_messages == 0:
            return False, 0.0

        tokens = tokenize(text)
        if not tokens:
            return False, 0.0

        prob_spam_prior = st.total_spam_messages / total_messages
        prob_ham_prior = st.total_ham_messages / total_messages
        significant = self._significant_tokens(
            tokens, prob_spam_prior, prob_ham_prior
        )

        spam_score = math.log(prob_spam_prior)
        ham_score = math.log(prob_ham_prior)
        for tok in significant:
            spam_l, ham_l = self._likelihoods(tok)
            spam_score += math.log(spam_l)
            ham_score += math.log(ham_l)

        n = len(tokens)
        if 0 < n < self.short_message_word_threshold:
            bonus = self.short_message_word_threshold / n
            ham_score += math.log(bonus)

        diff = spam_score - ham_score
        p_spam = 1.0 / (1.0 + math.exp(-diff))
        return p_spam >= self.probability_threshold, p_spam

    def _likelihoods(self, token: str) -> Tuple[float, float]:
        vocab = max(self.state.vocabulary_size, 1)
        spam_c = self.state.spam_counts.get(token, 0)
        ham_c = self.state.ham_counts.get(token, 0)
        spam_l = (spam_c + 1.0) / (self.state.total_spam_words + vocab)
        ham_l = (ham_c + 1.0) / (self.state.total_ham_words + vocab)
        return spam_l, ham_l

    def _significant_tokens(
        self, tokens: List[str], prob_spam_prior: float, prob_ham_prior: float
    ) -> List[str]:
        unique = list(dict.fromkeys(tokens))
        scored = []
        for tok in unique:
            spam_l, ham_l = self._likelihoods(tok)
            p_ws = spam_l * prob_spam_prior
            p_wh = ham_l * prob_ham_prior
            denom = p_ws + p_wh
            if denom <= 0:
                prob = 0.5
            else:
                prob = p_ws / denom
            scored.append((tok, abs(prob - 0.5)))
        scored.sort(key=lambda x: -x[1])
        return [t for t, _ in scored[: self.top_tokens]]
