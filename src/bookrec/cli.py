from __future__ import annotations

from pathlib import Path

import click
import pandas as pd

from bookrec.config import get_settings
from bookrec.data.load_raw import load_raw_dfs
from bookrec.data.clean_transform import run_full_clean
from bookrec.data.ingest_hybrid import initialize_and_ingest_hybrid
from bookrec.data.kaggle_download import download_to_raw
from bookrec.data.enrich_mongo import enrich_user_profiles, enrich_book_details


@click.group()
def cli():
    """BookRec project CLI."""


@cli.command()
@click.option("--data-dir", type=click.Path(path_type=Path), default=None, help="Directory with raw CSV files")
@click.option("--drop-existing/--no-drop-existing", default=False, help="Drop and recreate tables/collections")
def ingest(data_dir: Path | None, drop_existing: bool):
    """Load raw CSVs, clean, and ingest into MySQL + MongoDB (HYBRID)."""
    books, users, ratings = load_raw_dfs(data_dir)
    b, u, r = run_full_clean(books, users, ratings)
    initialize_and_ingest_hybrid(b, u, r, drop_existing=drop_existing)
    click.echo("Hybrid ingestion complete (MySQL + MongoDB).")


@cli.command()
@click.option("--dest-dir", type=click.Path(path_type=Path), default=None, help="Destination raw data directory")
@click.option("--file", "files", multiple=True, help="Specific dataset file(s) to fetch (e.g., Books.csv). Repeatable.")
def download_kaggle(dest_dir: Path | None, files: tuple[str, ...]):
    """Download Book Recommendation dataset files from Kaggle into data/raw using kagglehub."""
    saved = download_to_raw(file_paths=list(files) if files else None, dest_dir=dest_dir)
    for p in saved:
        click.echo(f"Saved: {p}")


@cli.command("enrich-mongo")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None, help="Directory with raw CSV files")
@click.option("--geocode/--no-geocode", default=False, help="Geocode user locations (slower)")
@click.option("--geocode-limit", type=int, default=50, help="Limit number of users to geocode for this run")
@click.option("--top-n", type=int, default=5, help="Top-N items for preferences")
@click.option("--good-threshold", type=int, default=7, help="Minimum rating to consider a book 'liked'")
def enrich_mongo_cmd(data_dir: Path | None, geocode: bool, geocode_limit: int, top_n: int, good_threshold: int):
    """Compute and upsert user_profiles and book_details into MongoDB.

    - user_profiles: rating_summary, rating_distribution, preferences, demographics, location fields
    - book_details: categories (from books CSV), avg_rating, num_ratings, publisher, year
    """
    from bookrec.data.clean_transform import run_full_clean
    from bookrec.data.load_raw import load_raw_dfs
    from bookrec.data.enrich_mongo import PrefConfig

    click.echo("Loading raw CSVs...")
    books, users, ratings = load_raw_dfs(data_dir)
    b, u, r = run_full_clean(books, users, ratings)

    cfg = PrefConfig(good_rating_threshold=good_threshold, top_n=top_n)
    click.echo("Enriching MongoDB user_profiles...")
    enrich_user_profiles(u, r, b, geocode=geocode, geocode_limit=geocode_limit, cfg=cfg)
    click.echo("Enriching MongoDB book_details...")
    enrich_book_details(b, r)
    click.echo("MongoDB enrichment complete.")


@cli.command()
@click.option("--user-id", type=int, required=True)
@click.option("--k", type=int, default=10)
def recommend(user_id: int, k: int):
    """Produce top-k recommendations for a user using HYBRID MySQL + MongoDB data."""
    from bookrec.data.mysql_db import Rating, Book, get_session_factory
    from bookrec.data.mongo_db import get_mongo_db
    from bookrec.models.collaborative import CFRecommender

    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        ratings = session.query(Rating).all()
        books = session.query(Book).all()
        if not ratings or not books:
            click.echo("MySQL DB is empty — run 'ingest' first.")
            return
        ratings_df = pd.DataFrame([{ "user_id": r.user_id, "isbn": r.isbn, "rating": r.rating } for r in ratings])
        all_items = [b.isbn for b in books]
        model = CFRecommender().fit(ratings_df)
        recs = model.recommend(user_id, all_items, k=k, exclude_seen=ratings_df)
        
        # Enrich with MongoDB user profile
        mongo_db = get_mongo_db()
        user_profile = mongo_db.user_profiles.find_one({"user_id": user_id})
        
        click.echo(f"Top-{k} recommendations for user {user_id}:")
        if user_profile:
            click.echo(f"  User preferences (MongoDB): {user_profile.get('preferences', {})}")
        for isbn, score in recs:
            click.echo(f"  {isbn}  score={score:.3f}")


if __name__ == "__main__":
    cli()
