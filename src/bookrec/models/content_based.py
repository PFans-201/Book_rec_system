from __future__ import annotations

from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class ContentBasedRecommender:
    def __init__(self, max_features: int = 5000, ngram_range: tuple[int, int] = (1, 2)):
        self.vectorizer = TfidfVectorizer(max_features=max_features, ngram_range=ngram_range, stop_words="english")
        self.item_index: dict[str, int] | None = None
        self.tfidf_matrix = None

    def fit(self, books: pd.DataFrame) -> "ContentBasedRecommender":
        # Expect columns: isbn, title, author
        texts = (books["title"].fillna("") + " " + books["author"].fillna("")).astype(str)
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)
        self.item_index = {isbn: idx for idx, isbn in enumerate(books["isbn"].tolist())}
        return self

    def similar_items(self, isbn: str, k: int = 10) -> List[Tuple[str, float]]:
        if self.item_index is None or self.tfidf_matrix is None:
            raise RuntimeError("Model not fitted")
        idx = self.item_index.get(isbn)
        if idx is None:
            return []
        sims = cosine_similarity(self.tfidf_matrix[idx], self.tfidf_matrix).ravel()
        top_idx = np.argsort(-sims)[: k + 1]  # include self
        results = []
        for j in top_idx:
            if j == idx:
                continue
            score = float(sims[j])
            other_isbn = list(self.item_index.keys())[list(self.item_index.values()).index(j)]
            results.append((other_isbn, score))
        return results[:k]
