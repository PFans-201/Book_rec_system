"""
Collaborative Filtering Recommendation System
Recommends books based on similar users' preferences.
Finds users with similar rating patterns and recommends their highly-rated books.
"""

from sqlalchemy import text
from collections import defaultdict
import math


def get_user_ratings(mysql_engine, user_id):
    """Get all ratings for a user as a dict {isbn: rating}"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT isbn, rating FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        return {row[0]: row[1] for row in result.fetchall()}


def find_similar_users(mysql_engine, target_user_id, min_common_books=5, limit=20):
    """
    Find users similar to target user based on rating correlation
    Uses Pearson correlation for users who rated at least min_common_books in common
    """
    target_ratings = get_user_ratings(mysql_engine, target_user_id)
    
    if not target_ratings:
        return []
    
    target_books = set(target_ratings.keys())
    
    # Find users who have rated some of the same books
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT user_id
            FROM ratings
            WHERE isbn IN :isbns AND user_id != :target_user_id
        """), {"isbns": tuple(target_books), "target_user_id": target_user_id})
        
        candidate_users = [row[0] for row in result.fetchall()]
    
    # Calculate similarity for each candidate
    similar_users = []
    
    for candidate_id in candidate_users[:500]:  # Limit candidates for performance
        candidate_ratings = get_user_ratings(mysql_engine, candidate_id)
        
        # Find common books
        common_books = target_books.intersection(set(candidate_ratings.keys()))
        
        if len(common_books) < min_common_books:
            continue
        
        # Calculate Pearson correlation
        target_vals = [target_ratings[isbn] for isbn in common_books]
        candidate_vals = [candidate_ratings[isbn] for isbn in common_books]
        
        # Mean-center the ratings
        target_mean = sum(target_vals) / len(target_vals)
        candidate_mean = sum(candidate_vals) / len(candidate_vals)

        
        target_centered = [r - target_mean for r in target_vals]
        candidate_centered = [r - candidate_mean for r in candidate_vals]
        
        # Compute correlation
        numerator = sum(t * c for t, c in zip(target_centered, candidate_centered))
        target_sq = sum(t * t for t in target_centered)
        candidate_sq = sum(c * c for c in candidate_centered)
        
        if target_sq == 0 or candidate_sq == 0:
            continue
        
        denominator = math.sqrt(target_sq * candidate_sq)
        correlation = numerator / denominator if denominator > 0 else 0
        
        if correlation > 0.3:  # Only consider positively correlated users
            similar_users.append({
                "user_id": candidate_id,
                "correlation": correlation,
                "common_books": len(common_books)
            })
    
    # Sort by correlation
    similar_users.sort(key=lambda x: x["correlation"], reverse=True)
    return similar_users[:limit]


def get_recommendations_from_similar_users(mysql_engine, target_user_id, similar_users, limit=10):
    """Get recommendations from similar users' highly-rated books"""
    
    # Get target user's rated books (to exclude)
    target_ratings = get_user_ratings(mysql_engine, target_user_id)
    rated_isbns = set(target_ratings.keys())
    
    # Collect recommendations weighted by similarity
    book_scores = defaultdict(lambda: {"score": 0.0, "raters": [], "avg_rating": 0.0})
    
    for similar_user in similar_users:
        user_id = similar_user["user_id"]
        similarity = similar_user["correlation"]
        
        # Get their highly-rated books
        with mysql_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT isbn, rating FROM ratings
                WHERE user_id = :user_id AND rating >= 7
            """), {"user_id": user_id})
            
            for isbn, rating in result.fetchall():
                if isbn not in rated_isbns:
                    # Weight by both rating and similarity
                    weighted_score = rating * similarity
                    book_scores[isbn]["score"] += weighted_score
                    book_scores[isbn]["raters"].append((user_id, rating, similarity))
                    book_scores[isbn]["avg_rating"] += rating
    
    # Compute average ratings and sort
    scored_books = []
    for isbn, data in book_scores.items():
        num_raters = len(data["raters"])
        if num_raters > 0:
            data["avg_rating"] = data["avg_rating"] / num_raters
            data["isbn"] = isbn
            scored_books.append(data)
    
    scored_books.sort(key=lambda x: (len(x["raters"]), x["score"]), reverse=True)
    return scored_books[:limit]


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
            "isbn": isbn,
            "title": title,
            "authors": authors,
            "publisher": publisher,
            "publication_year": pub_year,
            "score": rec["score"],
            "raters": rec["raters"],
            "avg_rating_from_similar": rec["avg_rating"],
            "metadata": book_meta
        })
    
    return enriched


def display_recommendations(target_user_id, similar_users, recommendations):
    """Display collaborative filtering recommendations"""
    print("\n" + "=" * 80)
    print("👥 COLLABORATIVE FILTERING RECOMMENDATIONS")
    print("=" * 80)
    print(f"\nBased on {len(similar_users)} similar users")
    print("Top similar users:")
    for i, user in enumerate(similar_users[:3], 1):
        print(f"  {i}. User {user['user_id']}: correlation={user['correlation']:.3f}, "
              f"{user['common_books']} books in common")
    
    print("\n" + "=" * 80)
    print("📚 RECOMMENDED BOOKS")
    print("=" * 80)
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['title']}")
        print(f"   ISBN: {rec['isbn']}")
        print(f"   Authors: {rec['authors']}")
        print(f"   Score: {rec['score']:.2f}")
        print(f"   Recommended by {len(rec['raters'])} similar users "
              f"(avg rating: {rec['avg_rating_from_similar']:.1f}/10)")
        
        # Show who recommended it
        print("   Recommended by:")
        for user_id, rating, similarity in rec['raters'][:3]:
            print(f"     • User {user_id} (similarity: {similarity:.2f}) rated it {rating}/10")
        
        # Show global metrics
        if rec.get('metadata') and 'rating_metrics' in rec['metadata']:
            rm = rec['metadata']['rating_metrics']
            print(f"   Global rating: {rm.get('r_avg', 'N/A')}/10 ({rm.get('r_count', 0)} total ratings)")

