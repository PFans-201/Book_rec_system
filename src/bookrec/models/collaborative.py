from __future__ import annotations

from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD


class CFRecommender:
    """Lightweight latent-factor CF using TruncatedSVD (scikit-learn).

    - Builds a user-item rating matrix (CSR sparse).
    - Applies TruncatedSVD to obtain item embeddings (Vt) and user projections (M @ Vt.T).
    - Scores with dot products in the latent space.
    """

    def __init__(self, n_factors: int = 100, random_state: int = 42):
        self.n_factors = n_factors
        self.random_state = random_state
        self.svd: TruncatedSVD | None = None
        self.user_index: dict[int, int] | None = None
        self.item_index: dict[str, int] | None = None
        self.index_item: list[str] | None = None
        self.user_factors: np.ndarray | None = None  # shape (n_users, n_factors)
        self.item_factors: np.ndarray | None = None  # shape (n_items, n_factors)

    def _build_matrix(self, ratings: pd.DataFrame) -> csr_matrix:
        users = ratings["user_id"].astype(int).unique().tolist()
        items = ratings["isbn"].astype(str).unique().tolist()
        self.user_index = {u: i for i, u in enumerate(users)}
        self.item_index = {it: i for i, it in enumerate(items)}
        self.index_item = items

        row = ratings["user_id"].map(self.user_index).to_numpy()
        col = ratings["isbn"].map(self.item_index).to_numpy()
        data = ratings["rating"].astype(float).to_numpy()
        n_users, n_items = len(users), len(items)
        return csr_matrix((data, (row, col)), shape=(n_users, n_items))

    def fit(self, ratings: pd.DataFrame) -> "CFRecommender":
        if ratings.empty:
            raise ValueError("ratings is empty")
        M = self._build_matrix(ratings)
        n_comp = min(self.n_factors, min(M.shape) - 1) if min(M.shape) > 1 else 1
        self.svd = TruncatedSVD(n_components=max(1, n_comp), random_state=self.random_state)
        # Fit on items (columns): SVD on M gives Vt (components_)
        self.svd.fit(M)
        # item_factors: (n_items, n_factors)
        self.item_factors = self.svd.components_.T
        # user_factors: project M into latent space: M @ Vt.T
        self.user_factors = M @ self.item_factors
        return self

    def _score(self, uidx: int, iidx: int) -> float:
        assert self.user_factors is not None and self.item_factors is not None
        return float(self.user_factors[uidx] @ self.item_factors[iidx])

    def predict_for_user(self, user_id: int, candidate_isbns: Iterable[str]) -> List[Tuple[str, float]]:
        if (
            self.user_index is None
            or self.item_index is None
            or self.user_factors is None
            or self.item_factors is None
        ):
            raise RuntimeError("Model not fitted")
        if user_id not in self.user_index:
            # cold-start user -> return empty list
            return []
        uidx = self.user_index[user_id]
        preds = []
        for isbn in candidate_isbns:
            if isbn in self.item_index:
                iidx = self.item_index[isbn]
                preds.append((isbn, self._score(uidx, iidx)))
        preds.sort(key=lambda x: x[1], reverse=True)
        return preds

    def recommend(
        self,
        user_id: int,
        all_items: Iterable[str],
        k: int = 10,
        exclude_seen: pd.DataFrame | None = None,
    ) -> List[Tuple[str, float]]:
        candidates = set(all_items)
        if exclude_seen is not None and not exclude_seen.empty:
            seen = set(
                exclude_seen.loc[exclude_seen["user_id"] == user_id, "isbn"].astype(str).unique().tolist()
            )
            candidates -= seen
        return self.predict_for_user(user_id, candidates)[:k]
