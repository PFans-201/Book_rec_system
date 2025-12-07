"""
Cold-Start Recommendation System
Provides recommendations for new users with few or no ratings.
Uses demographic information and global popularity.
"""

from sqlalchemy import text


def get_user_demographics(mysql_engine, user_id):
    """Get user demographic information"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT age_group, gender, location
            FROM users WHERE user_id = :user_id
        """), {"user_id": user_id})
        row = result.fetchone()

        if row:
            return {
                "age_group": row[0],
                "gender": row[1],
                "location": row[2]
            }
    return None


def get_user_rating_count(mysql_engine, user_id):
    """Check if user is truly cold-start"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        count = result.fetchone()[0]
        return count if count else 0


def find_similar_demographic_users(mysql_engine, demographics, limit=100, explain = False):
    """Find users with similar demographics"""
    conditions = []
    params = {}

    if demographics.get("age_group"):
        conditions.append("age_group = :age_group")
        params["age_group"] = demographics["age_group"]

    if demographics.get("gender"):
        conditions.append("gender = :gender")
        params["gender"] = demographics["gender"]

    if not conditions:
        # No demographics available, return random active users
        with mysql_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT user_id FROM users
                WHERE has_ratings = TRUE
                ORDER BY RAND()
                LIMIT :limit
            """), {"limit": limit})
            return [{"user_id": row[0], "match": "random"} for row in result.fetchall()]

    where_clause = " AND ".join(conditions)
    params["limit"] = limit

    with mysql_engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT user_id FROM users
            WHERE {where_clause} AND has_ratings = TRUE
            LIMIT :limit
        """), params)

        similar = [{"user_id": row[0], "match": "demographic"} for row in result.fetchall()]

        # If not enough, add random users
        if len(similar) < limit // 2:
            result = conn.execute(text("""
                SELECT user_id FROM users
                WHERE has_ratings = TRUE
                ORDER BY RAND()
                LIMIT :extra_limit
            """), {"extra_limit": limit - len(similar)})
            similar.extend([{"user_id": row[0], "match": "random"} for row in result.fetchall()])
        if explain:
            # para mongodb ...
            # para mysql ...
        return similar


def get_demographic_favorites(mysql_engine, similar_users, min_rating=7, limit=100):
    """Get books highly rated by similar demographic users"""
    if not similar_users:
        return []

    user_ids = tuple([u["user_id"] for u in similar_users])

    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                isbn,
                COUNT(*) as demographic_count,
                AVG(rating) as demographic_avg
            FROM ratings
            WHERE user_id IN :user_ids AND rating >= :min_rating
            GROUP BY isbn
            HAVING demographic_count >= 5
            ORDER BY demographic_count DESC, demographic_avg DESC
            LIMIT :limit
        """), {
            "user_ids": user_ids,
            "min_rating": min_rating,
            "limit": limit
        })

        favorites = []
        for row in result.fetchall():
            isbn, count, avg_rating = row
            favorites.append({
                "isbn": isbn,
                "demographic_count": count,
                "demographic_avg": avg_rating
            })

        return favorites


def boost_with_global_popularity(mongo_db, favorites, popularity_weight=0.3):
    """Boost scores with global popularity from MongoDB"""
    for fav in favorites:
        book_meta = mongo_db.books_metadata.find_one({"_id": fav["isbn"]})

        if book_meta and "rating_metrics" in book_meta:
            rm = book_meta["rating_metrics"]
            rating_score = rm.get("rating_score", 0)

            # Combined score: demographic preference + global popularity
            base_score = fav["demographic_count"] * fav["demographic_avg"]
            popularity_boost = rating_score * 10 * popularity_weight

            fav["total_score"] = base_score + popularity_boost
            fav["global_rating_score"] = rating_score
        else:
            fav["total_score"] = fav["demographic_count"] * fav["demographic_avg"]
            fav["global_rating_score"] = 0

    # Resort by total score
    favorites.sort(key=lambda x: x["total_score"], reverse=True)
    return favorites


def enrich_recommendations(mysql_engine, mongo_db, recommendations):
    """Add book details from MySQL and MongoDB"""
    enriched = []

    for rec in recommendations:
        isbn = rec["isbn"]

        # Get book details from MySQL
        with mysql_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT title, authors, publisher, publication_year
                FROM books WHERE isbn = :isbn
            """), {"isbn": isbn})
            book_row = result.fetchone()

        if not book_row:
            continue

        title, authors, publisher, pub_year = book_row

        # Get metadata from MongoDB
        book_meta = mongo_db.books_metadata.find_one({"_id": isbn})

        enriched.append({
            **rec,
            "title": title,
            "authors": authors,
            "publisher": publisher,
            "publication_year": pub_year,
            "metadata": book_meta
        })

    return enriched


def get_cold_start_recommendations(mysql_engine, mongo_db, user_id, limit=10):
    """
    Get recommendations for a cold-start user based on demographics and global popularity.
    """
    # 1. Get user demographics
    demographics = get_user_demographics(mysql_engine, user_id)
    
    if not demographics:
        print(f"User {user_id} has no demographic info. Falling back to global trending.")
        # Fallback to trending (circular import avoidance)
        from .recommendation_trending import get_trending_recommendations
        return get_trending_recommendations(mysql_engine, mongo_db, limit=limit)

    # 2. Find similar users based on demographics
    similar_users = find_similar_demographic_users(mysql_engine, demographics)
    
    # 3. Get books liked by these similar users
    favorites = get_demographic_favorites(mysql_engine, similar_users, limit=limit*2)
    
    # 4. Boost with global popularity
    boosted = boost_with_global_popularity(mongo_db, favorites)
    
    # 5. Enrich with metadata
    enriched = enrich_recommendations(mysql_engine, mongo_db, boosted[:limit])
    
    return enriched


