from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable, Sequence

CJK = re.compile(r"[\u4e00-\u9fff]")
ASCII_WORD = re.compile(r"[a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    """中文用字符二元组 + 单字，英文/数字按词切。

    不引 jieba：语料是口语转写，分词的边界噪声比二元组更大，
    而 BM25 只用来兜关键词召回，粗一点没关系。
    """
    text = (text or "").lower()
    tokens: list[str] = []
    for word in ASCII_WORD.findall(text):
        tokens.append(word)
    chars = CJK.findall(text)
    tokens.extend(chars)
    tokens.extend(a + b for a, b in zip(chars, chars[1:]))
    return tokens


class BM25:
    def __init__(self, docs: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_tokens = [Counter(tokenize(d)) for d in docs]
        self.doc_len = [sum(c.values()) for c in self.doc_tokens]
        self.avg_len = (sum(self.doc_len) / len(docs)) if docs else 0.0
        self.df: Counter[str] = Counter()
        for counter in self.doc_tokens:
            self.df.update(counter.keys())
        self.n = len(docs)

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = 50) -> list[tuple[int, float]]:
        terms = tokenize(query)
        if not terms or not self.doc_tokens:
            return []
        scores: list[tuple[int, float]] = []
        for index, counter in enumerate(self.doc_tokens):
            length = self.doc_len[index] or 1
            score = 0.0
            for term in terms:
                tf = counter.get(term)
                if not tf:
                    continue
                norm = self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
                score += self._idf(term) * tf * (self.k1 + 1) / (tf + norm)
            if score > 0:
                scores.append((index, score))
        scores.sort(key=lambda pair: -pair[1])
        return scores[:k]


def rrf_fuse(
    rankings: Iterable[list[tuple[int, float]]], k: int = 60, size: int = 30
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion：只看名次不看分数，避免两路分数量纲不同。"""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, (index, _score) in enumerate(ranking):
            fused[index] = fused.get(index, 0.0) + 1.0 / (k + rank + 1)
    merged = sorted(fused.items(), key=lambda pair: -pair[1])
    return merged[:size]
