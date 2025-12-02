from __future__ import annotations

from datetime import datetime

import pandas as pd

from bookrec.data.mysql_db import Book, Rating, User, get_session_factory, init_mysql_db
from bookrec.utils.demographics import age_to_category, assign_gender
from bookrec.data.mongo_db import get_mongo_db, init_mongo_collections
from bookrec.utils.geographic import GeographicTransformer


def ingest_to_mysql(books: pd.DataFrame, users: pd.DataFrame, ratings: pd.DataFrame, drop_existing: bool = False) -> None:
    """Load structured data into MySQL."""
    init_mysql_db(drop_existing=drop_existing)
    SessionLocal = get_session_factory()
    
    with SessionLocal() as session:
        # Insert users
        for row in users.itertuples(index=False):
            raw_age = getattr(row, "age", None)
            # Convert to int if not None/NaN
            try:
                age_val = int(raw_age) if raw_age is not None and str(raw_age).lower() != 'nan' else None
            except Exception:
                age_val = None
            age_cat = age_to_category(age_val)
            gender = assign_gender(int(getattr(row, "user_id")))
            user = User(
                user_id=int(getattr(row, "user_id")),
                age=age_val,
                location=getattr(row, "location", None),
                age_category=age_cat,
                gender=gender,
            )
            session.merge(user)
        session.commit()
        
        # Insert books (core metadata only)
        for row in books.itertuples(index=False):
            book = Book(
                isbn=str(getattr(row, "isbn")),
                title=getattr(row, "title", None),
                author=getattr(row, "author", None),
                year=getattr(row, "year", None),
                publisher=getattr(row, "publisher", None),
            )
            session.merge(book)
        session.commit()
        
        # Insert ratings (transactional log)
        for row in ratings.itertuples(index=False):
            rating = Rating(
                user_id=int(getattr(row, "user_id")),
                isbn=str(getattr(row, "isbn")),
                rating=float(getattr(row, "rating")),
            )
            session.merge(rating)
        session.commit()


def ingest_to_mongodb(books: pd.DataFrame, users: pd.DataFrame, ratings: pd.DataFrame, drop_existing: bool = False) -> None:
    """Load semi-structured data into MongoDB.
    
    - user_profiles: preferences derived from ratings, reading history
    - book_details: extended metadata (can be enriched later)
    - interaction_logs: simulate some view/click events from ratings
    """
    if drop_existing:
        from bookrec.data.mongo_db import drop_mongo_collections
        drop_mongo_collections()
    
    init_mongo_collections()
    db = get_mongo_db()
    
    # user_profiles: generate preference tags from ratings and include geocoded location
    transformer = GeographicTransformer()
    user_docs = []
    for uid in users["user_id"].unique():
        user_row_df = users.loc[users["user_id"] == uid]
        if user_row_df.empty:
            continue
        user_row = user_row_df.iloc[0]
        raw_location = user_row.get("location") if "location" in user_row.index else None
        age_val = user_row.get("age") if "age" in user_row.index else None
        try:
            age_int = int(age_val) if age_val is not None and str(age_val).lower() != 'nan' else None
        except Exception:
            age_int = None
        age_cat = age_to_category(age_int)
        gender = assign_gender(int(uid))

        # Geocode location (may return None)
        geo = transformer.geocode_location(raw_location) if raw_location and str(raw_location).strip() != "" else None
        location_field = None
        if geo:
            location_field = {
                "type": "Point",
                "coordinates": geo["coordinates"],  # [lng, lat]
                "display_name": geo.get("display_name"),
                "country": geo.get("country"),
            }

        user_ratings = ratings[ratings["user_id"] == uid]
        top_books = user_ratings.nlargest(5, "rating")["isbn"].tolist()
        user_doc = {
            "user_id": int(uid),
            "preferences": {
                "favorite_books": top_books,
                "avg_rating": float(user_ratings["rating"].mean()) if len(user_ratings) > 0 else None,
                "total_ratings": len(user_ratings),
            },
            "reading_history": [
                {"isbn": str(r.isbn), "rating": float(r.rating)}
                for r in user_ratings.itertuples(index=False)
            ],
            "location": location_field,
            "raw_location": raw_location,
            "demographics": {
                "age": age_int,
                "age_category": age_cat,
                "gender": gender,
            },
            "updated_at": datetime.now(),
        }
        user_docs.append(user_doc)
    if user_docs:
        db.user_profiles.insert_many(user_docs, ordered=False)
    
    # book_details: nested metadata (can add categories, reviews later)
    book_docs = []
    for row in books.itertuples(index=False):
        isbn = str(getattr(row, "isbn"))
        book_ratings = ratings[ratings["isbn"] == isbn]
        book_docs.append({
            "isbn": isbn,
            "extended_metadata": {
                "description": None,  # placeholder for enrichment
                "categories": [],
                "avg_rating": float(book_ratings["rating"].mean()) if len(book_ratings) > 0 else None,
                "num_ratings": len(book_ratings),
            },
            "reviews": [],  # placeholder for user reviews
            "updated_at": datetime.now(),
        })
    if book_docs:
        db.book_details.insert_many(book_docs, ordered=False)
    
    # interaction_logs: simulate view events from ratings (for demo)
    interaction_docs = []
    for row in ratings.head(1000).itertuples(index=False):  # sample for demo
        interaction_docs.append({
            "user_id": int(getattr(row, "user_id")),
            "isbn": str(getattr(row, "isbn")),
            "event_type": "rate",
            "timestamp": datetime.now(),
            "metadata": {"rating_value": float(getattr(row, "rating"))},
        })
    if interaction_docs:
        db.interaction_logs.insert_many(interaction_docs, ordered=False)


def initialize_and_ingest_hybrid(
    books: pd.DataFrame, users: pd.DataFrame, ratings: pd.DataFrame, drop_existing: bool = False
) -> None:
    """Ingest data into both MySQL and MongoDB with shared IDs."""
    print("Ingesting structured data into MySQL...")
    ingest_to_mysql(books, users, ratings, drop_existing=drop_existing)
    print("Ingesting semi-structured data into MongoDB...")
    ingest_to_mongodb(books, users, ratings, drop_existing=drop_existing)
    print("Hybrid ingestion complete.")
