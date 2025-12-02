from __future__ import annotations

import ast
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from bookrec.data.mongo_db import get_mongo_db, init_mongo_collections
from bookrec.utils.demographics import age_to_category, assign_gender
from bookrec.utils.geographic import GeographicTransformer


@dataclass
class PrefConfig:
    good_rating_threshold: int = 7
    top_n: int = 5


def _safe_categories(val) -> List[str]:
    """Parse categories column which may be a string repr of list like "['Fiction']"."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        try:
            parsed = ast.literal_eval(val)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            # fallback: split by comma
            return [s.strip() for s in val.split(',') if s.strip()]
    return []


def build_book_lookup(books_df: pd.DataFrame) -> Dict[str, Dict]:
    """Build a lookup from isbn -> metadata (author, publisher, year, categories)."""
    df = books_df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    # Normalize column names if needed
    rename = {
        "book-title": "title",
        "book author": "author",
        "book-author": "author",
        "year-of-publication": "year",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    lookup: Dict[str, Dict] = {}
    for row in df.itertuples(index=False):
        isbn = str(getattr(row, "isbn"))
        lookup[isbn] = {
            "title": getattr(row, "title", None),
            "author": getattr(row, "author", None),
            "publisher": getattr(row, "publisher", None),
            "year": getattr(row, "year", None),
            "categories": _safe_categories(getattr(row, "categories", None)),
        }
    return lookup


def rating_summary_and_distribution(user_ratings: pd.DataFrame) -> Tuple[Dict, Dict[str, int]]:
    """Compute avg/total and per-score distribution 0..10."""
    if user_ratings.empty:
        return {"avg_rating": None, "total_ratings": 0}, {str(i): 0 for i in range(0, 11)}

    avg = float(user_ratings["rating"].mean())
    total = int(user_ratings.shape[0])
    dist = Counter(user_ratings["rating"].astype(int).tolist())
    dist_dict = {str(i): int(dist.get(i, 0)) for i in range(0, 11)}
    return {"avg_rating": avg, "total_ratings": total}, dist_dict


def derive_preferences(user_ratings: pd.DataFrame, book_lu: Dict[str, Dict], cfg: PrefConfig) -> Dict:
    """Derive preference signals from user's ratings joined with book metadata."""
    if user_ratings.empty:
        return {
            "favorite_books": [],
            "preferred_genres": [],
            "preferred_authors": [],
            "preferred_publishers": [],
            "preferred_years_of_publication": {"min": None, "max": None},
        }

    # Favorite books: top-N by rating, then by count
    top_books = (
        user_ratings.sort_values(["rating"], ascending=[False])["isbn"].astype(str).head(cfg.top_n).tolist()
    )

    # Consider only good ratings for preferences
    liked = user_ratings[user_ratings["rating"] >= cfg.good_rating_threshold]

    # Accumulators
    genre_ct = Counter()
    author_ct = Counter()
    publisher_ct = Counter()
    years = []

    for row in liked.itertuples(index=False):
        meta = book_lu.get(str(getattr(row, "isbn")), {})
        for g in meta.get("categories", []) or []:
            genre_ct[g] += 1
        a = meta.get("author")
        if a:
            author_ct[a] += 1
        p = meta.get("publisher")
        if p:
            publisher_ct[p] += 1
        y = meta.get("year")
        try:
            y = int(y) if y is not None and str(y).lower() != "nan" else None
        except Exception:
            y = None
        if y is not None and 1000 <= y <= 2100:
            years.append(y)

    preferred = {
        "favorite_books": top_books,
        "preferred_genres": [g for g, _ in genre_ct.most_common(cfg.top_n)],
        "preferred_authors": [a for a, _ in author_ct.most_common(cfg.top_n)],
        "preferred_publishers": [p for p, _ in publisher_ct.most_common(cfg.top_n)],
        "preferred_years_of_publication": {
            "min": int(min(years)) if years else None,
            "max": int(max(years)) if years else None,
        },
    }
    return preferred


def parse_city_state_country(location: Optional[str]) -> Dict[str, Optional[str]]:
    if not location or not isinstance(location, str):
        return {"city": None, "state": None, "country": None}
    parts = [p.strip() for p in location.split(',')]
    # normalize to 3 parts
    while len(parts) < 3:
        parts.append(None)
    city, state, country = parts[0], parts[1], parts[2]
    # Normalize casing
    if country:
        country = country.upper()
    return {"city": city, "state": state, "country": country}


def enrich_user_profiles(
    users_df: pd.DataFrame,
    ratings_df: pd.DataFrame,
    books_df: pd.DataFrame,
    geocode: bool = False,
    geocode_limit: Optional[int] = None,
    cfg: PrefConfig = PrefConfig(),
) -> None:
    """Compute and upsert user_profiles documents with preferences, summaries, and location.

    This will create or update documents in MongoDB user_profiles collection.
    """
    init_mongo_collections()
    db = get_mongo_db()

    # Build lookups
    book_lu = build_book_lookup(books_df)

    # Prepare ratings grouped by user
    ratings_df = ratings_df.copy()
    ratings_df["rating"] = pd.to_numeric(ratings_df["rating"], errors="coerce")
    ratings_df = ratings_df.dropna(subset=["user_id", "isbn", "rating"])  # safety

    # Optional geocoder
    gt = GeographicTransformer(rate_limit_delay=1.0) if geocode else None

    # Iterate users
    count = 0
    for uid in users_df["user_id"].astype(int).unique().tolist():
        urows = users_df[users_df["user_id"] == uid]
        if urows.empty:
            continue
        u = urows.iloc[0]
        user_r = ratings_df[ratings_df["user_id"] == uid]

        # summaries
        rating_sum, rating_dist = rating_summary_and_distribution(user_r)
        prefs = derive_preferences(user_r, book_lu, cfg)

        # demographics
        age_val = u.get("age")
        try:
            age_int = int(age_val) if age_val is not None and str(age_val).lower() != "nan" else None
        except Exception:
            age_int = None
        age_cat = age_to_category(age_int)
        gender = assign_gender(int(uid))

        # location parse and optional geocode
        raw_loc = u.get("location") if "location" in u.index else None
        city_state_cty = parse_city_state_country(raw_loc)
        loc_doc = None
        if geocode and (geocode_limit is None or count < geocode_limit):
            g = gt.geocode_location(raw_loc) if raw_loc and str(raw_loc).strip() else None
            if g:
                loc_doc = {
                    "type": "Point",
                    "coordinates": g["coordinates"],  # [lng, lat]
                    "display_name": g.get("display_name"),
                    "country": g.get("country"),
                }

        # Build document
        doc = {
            "user_id": int(uid),
            "rating_summary": rating_sum,
            "preferences": prefs,
            "rating_history": [
                {"isbn": str(r.isbn), "rating": float(r.rating)} for r in user_r.itertuples(index=False)
            ],
            "rating_distribution": rating_dist,
            "raw_location": raw_loc,
            "location": loc_doc,  # GeoJSON point if available
            "location_fields": city_state_cty,  # city/state/country parsed from string
            "demographics": {
                "age": age_int,
                "age_category": age_cat,
                "gender": gender,
            },
        }

        # Upsert into MongoDB
        db.user_profiles.update_one({"user_id": int(uid)}, {"$set": doc}, upsert=True)
        count += 1


def enrich_book_details(books_df: pd.DataFrame, ratings_df: pd.DataFrame) -> None:
    """Upsert book_details with categories, avg_rating, num_ratings, publisher, year."""
    init_mongo_collections()
    db = get_mongo_db()

    books_df = books_df.copy()
    ratings_df = ratings_df.copy()

    # Normalize
    books_df.columns = [c.strip().lower() for c in books_df.columns]
    ratings_df["rating"] = pd.to_numeric(ratings_df["rating"], errors="coerce")

    # Build ratings aggregates per isbn
    agg = (
        ratings_df.dropna(subset=["isbn", "rating"]).groupby("isbn")["rating"].agg(["mean", "count"]).reset_index()
    )
    agg = agg.rename(columns={"mean": "avg_rating", "count": "num_ratings"})
    r_lu = {str(r.isbn): {"avg_rating": float(r.avg_rating), "num_ratings": int(r.num_ratings)} for r in agg.itertuples(index=False)}

    for row in books_df.itertuples(index=False):
        isbn = str(getattr(row, "isbn"))
        categories = _safe_categories(getattr(row, "categories", None))
        publisher = getattr(row, "publisher", None)
        year = getattr(row, "year", None) if hasattr(row, "year") else getattr(row, "year_of_publication", None)
        try:
            year = int(year) if year is not None and str(year).lower() != "nan" else None
        except Exception:
            year = None

        rating_meta = r_lu.get(isbn, {"avg_rating": None, "num_ratings": 0})

        doc = {
            "isbn": isbn,
            "metadata": {
                "genres": categories,
                "avg_rating": rating_meta.get("avg_rating"),
                "num_ratings": rating_meta.get("num_ratings"),
                "publication_year": year,
                "publisher": publisher,
            },
        }
        # Upsert
        db.book_details.update_one({"isbn": isbn}, {"$set": doc}, upsert=True)
