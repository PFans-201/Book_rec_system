from __future__ import annotations

import pandas as pd
from bookrec.data.db import Book, Rating, User, get_engine, get_session_factory, init_db


def ingest_users(df: pd.DataFrame) -> int:
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        # Upsert-like behavior via merge loop for portability
        count = 0
        for row in df.itertuples(index=False):
            user = User(user_id=int(getattr(row, "user_id")))
            user.age = getattr(row, "age", None)
            user.location = getattr(row, "location", None)
            session.merge(user)
            count += 1
        session.commit()
        return count


def ingest_books(df: pd.DataFrame) -> int:
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        count = 0
        for row in df.itertuples(index=False):
            book = Book(
                isbn=str(getattr(row, "isbn")),
                title=getattr(row, "title", None),
                author=getattr(row, "author", None),
                year=getattr(row, "year", None),
                publisher=getattr(row, "publisher", None),
            )
            session.merge(book)
            count += 1
        session.commit()
        return count


def ingest_ratings(df: pd.DataFrame) -> int:
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        count = 0
        for row in df.itertuples(index=False):
            rating = Rating(
                user_id=int(getattr(row, "user_id")),
                isbn=str(getattr(row, "isbn")),
                rating=float(getattr(row, "rating")),
            )
            session.merge(rating)
            count += 1
        session.commit()
        return count


def initialize_and_ingest(books: pd.DataFrame, users: pd.DataFrame, ratings: pd.DataFrame, drop_existing: bool = False) -> None:
    """Create tables and ingest all dataframes into the DB."""
    init_db(drop_existing=drop_existing)
    ingest_users(users)
    ingest_books(books)
    ingest_ratings(ratings)
