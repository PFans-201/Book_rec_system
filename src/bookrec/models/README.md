# bookrec.models

Recommendation models.

- `collaborative.py` – SVD-based collaborative filtering via scikit-surprise. Produces top-N recommendations per user.
- `content_based.py` – TF-IDF of title+author with cosine similarity for item-item recommendations.

Both models are light and easy to explain for a database-centric course, while demonstrating complementary approaches.
