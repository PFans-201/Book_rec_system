from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from bookrec.config import get_settings

EXPECTED_FILENAMES = {
    "books": ["Books.csv", "BX-Books.csv"],
    "users": ["Users.csv", "BX-Users.csv"],
    "ratings": ["Ratings.csv", "BX-Book-Ratings.csv"],
}


def _resolve_first_existing(base: Path, candidates: list[str]) -> Path:
    for name in candidates:
        p = base / name
        if p.exists():
            return p
    raise FileNotFoundError(f"None of {candidates} found under {base}")


def load_raw_dfs(data_dir: Path | None = None) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load raw CSVs from Kaggle Book Recommendation dataset.

    Returns:
        (books_df, users_df, ratings_df)
    """
    settings = get_settings()
    base = Path(data_dir) if data_dir else settings.raw_dir

    books_path = _resolve_first_existing(base, EXPECTED_FILENAMES["books"])
    users_path = _resolve_first_existing(base, EXPECTED_FILENAMES["users"])
    ratings_path = _resolve_first_existing(base, EXPECTED_FILENAMES["ratings"])

    # The CSVs can be encoded with latin-1
    books = pd.read_csv(books_path, sep=";|,", engine="python", encoding="latin-1", on_bad_lines="skip")
    users = pd.read_csv(users_path, sep=";|,", engine="python", encoding="latin-1", on_bad_lines="skip")
    ratings = pd.read_csv(ratings_path, sep=";|,", engine="python", encoding="latin-1", on_bad_lines="skip")

    return books, users, ratings
