import pandas as pd

from bookrec.data.clean_transform import clean_books, clean_users, clean_ratings, apply_min_activity_filters


def test_clean_and_filter_pipeline():
    books = pd.DataFrame([
        {"isbn": "A", "book-title": "Title A", "book-author": "Auth", "year-of-publication": 1999},
        {"isbn": "B", "book-title": "Title B", "book-author": "Auth", "year-of-publication": 2028},  # invalid year
    ])
    users = pd.DataFrame([
        {"user-id": 1, "age": 25, "location": "X"},
        {"user-id": 2, "age": 200, "location": "Y"},  # invalid age
    ])
    ratings = pd.DataFrame([
        {"user-id": 1, "isbn": "A", "book-rating": 8},
        {"user-id": 1, "isbn": "B", "book-rating": 6},
        {"user-id": 2, "isbn": "A", "book-rating": 7},
    ])

    b = clean_books(books)
    u = clean_users(users)
    r = clean_ratings(ratings)

    assert set(b.columns) >= {"isbn", "title", "author", "year"}
    assert b.loc[b["isbn"] == "B", "year"].isna().all()  # invalid year nulled

    assert set(u.columns) >= {"user_id", "age", "location"}
    assert u.loc[u["user_id"] == 2, "age"].isna().all()  # invalid age nulled

    assert set(r.columns) >= {"user_id", "isbn", "rating"}

    r2 = apply_min_activity_filters(r, min_user_ratings=2, min_item_ratings=1)
    # Only user 1 has 2 interactions (with A and B)
    # Both ISBNs A and B appear at least once => both kept
    assert r2["user_id"].nunique() == 1
    assert r2["isbn"].nunique() == 2
