import pandas as pd

from bookrec.models.collaborative import CFRecommender


def test_cf_smoke():
    ratings = pd.DataFrame([
        {"user_id": 1, "isbn": "A", "rating": 8},
        {"user_id": 1, "isbn": "B", "rating": 6},
        {"user_id": 2, "isbn": "A", "rating": 7},
        {"user_id": 2, "isbn": "C", "rating": 9},
    ])

    model = CFRecommender(n_factors=10).fit(ratings)
    candidates = ["A", "B", "C", "D"]
    recs = model.recommend(user_id=1, all_items=candidates, k=3, exclude_seen=ratings)
    assert len(recs) <= 3
    assert all(isinstance(isbn, str) and isinstance(score, float) for isbn, score in recs)
