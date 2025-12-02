from __future__ import annotations

from typing import Iterable, List, Sequence


def precision_at_k(recommended: Sequence[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_k = recommended[:k]
    hits = sum(1 for x in top_k if x in relevant)
    return hits / k


def recall_at_k(recommended: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top_k = recommended[:k]
    hits = sum(1 for x in top_k if x in relevant)
    return hits / len(relevant)


def average_precision(recommended: Sequence[str], relevant: set[str], k: int) -> float:
    score = 0.0
    hits = 0
    for i, item in enumerate(recommended[:k], start=1):
        if item in relevant:
            hits += 1
            score += hits / i
    return score / max(1, len(relevant))


def ndcg_at_k(recommended: Sequence[str], relevant: set[str], k: int) -> float:
    import math

    def dcg(items: Sequence[str]) -> float:
        return sum((1.0 if x in relevant else 0.0) / math.log2(i + 1) for i, x in enumerate(items, start=1))

    ideal = sorted(recommended[:k], key=lambda x: (x in relevant), reverse=True)
    idcg = dcg(ideal)
    if idcg == 0:
        return 0.0
    return dcg(recommended[:k]) / idcg
