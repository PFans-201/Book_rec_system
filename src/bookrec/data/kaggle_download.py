from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
from kagglehub import KaggleDatasetAdapter, load_dataset

from bookrec.config import get_settings

DATASET = "arashnic/book-recommendation-dataset"
DEFAULT_FILES = ["Books.csv", "Users.csv", "Ratings.csv"]


def download_to_raw(file_paths: Iterable[str] | None = None, dest_dir: Path | None = None) -> list[Path]:
    """Download selected files from Kaggle dataset into data/raw.

    Args:
        file_paths: iterable of file names within the dataset. Defaults to Books/Users/Ratings.
        dest_dir: override destination directory; defaults to settings.raw_dir.
    Returns:
        List of saved file paths.
    """
    settings = get_settings()
    dst = Path(dest_dir) if dest_dir else settings.raw_dir
    dst.mkdir(parents=True, exist_ok=True)

    targets = list(file_paths) if file_paths else DEFAULT_FILES
    saved: list[Path] = []
    for fp in targets:
        df = load_dataset(KaggleDatasetAdapter.PANDAS, DATASET, fp)
        out = dst / fp
        # Ensure CSV with utf-8 encoding and separator comma for downstream
        df.to_csv(out, index=False)
        saved.append(out)
    return saved
