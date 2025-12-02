from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from project root if present
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    # Data paths
    data_dir: Path = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
    raw_dir: Path = data_dir / "raw"
    interim_dir: Path = data_dir / "interim"
    processed_dir: Path = data_dir / "processed"

    # MySQL (required by professor) - structured transactional data
    mysql_host: str = os.getenv("MYSQL_HOST", "localhost")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "bookrec")
    
    # MongoDB (required by professor) - semi-structured flexible data
    mongo_host: str = os.getenv("MONGO_HOST", "localhost")
    mongo_port: int = int(os.getenv("MONGO_PORT", "27017"))
    mongo_database: str = os.getenv("MONGO_DATABASE", "bookrec")
    mongo_uri: str = os.getenv("MONGO_URI", f"mongodb://{mongo_host}:{mongo_port}/")

    # Model / evaluation
    min_user_ratings: int = int(os.getenv("MIN_USER_RATINGS", "5"))
    min_item_ratings: int = int(os.getenv("MIN_ITEM_RATINGS", "5"))
    test_size: float = float(os.getenv("TEST_SIZE", "0.2"))
    random_state: int = int(os.getenv("RANDOM_STATE", "42"))


def get_settings() -> Settings:
    return Settings()
