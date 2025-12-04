"""
Hybrid Recommendation System
Combines content-based, collaborative filtering, and popularity signals
Provides weighted recommendations with configurable strategy weights.
"""

from pathlib import Path
import sys
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import argparse
from collections import defaultdict, Counter
import math

# Setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# Database connections
db_name = os.getenv("DB_NAME", "bookrec")
host = os.getenv("HOST", "localhost")
msql_user = os.getenv("MSQL_USER")
msql_password = os.getenv("MSQL_PASSWORD")
msql_port = os.getenv("MSQL_PORT", "3306")
mdb_user = os.getenv("MDB_USER")
mdb_password = os.getenv("MDB_PASSWORD")
mdb_cluster = os.getenv("MDB_CLUSTER")
mdb_appname = os.getenv("MDB_APPNAME", "Cluster0")
mdb_use_atlas = os.getenv("MDB_USE_ATLAS", "false").lower() == "true"

mysql_engine = create_engine(
    f"mysql+mysqlconnector://{msql_user}:{msql_password}@{host}:{msql_port}/{db_name}"
)

if mdb_use_atlas:
    mongodb_uri = f"mongodb+srv://{mdb_user}:{mdb_password}@{mdb_cluster}/?retryWrites=true&w=majority&appName={mdb_appname}"
    mongo_client = MongoClient(mongodb_uri, server_api=ServerApi('1'))
else:
    mongodb_uri = f"mongodb://{mdb_user}:{mdb_password}@{host}:27017/"
    mongo_client = MongoClient(mongodb_uri)

mongo_db = mongo_client[db_name]


def get_user_preferences(user_id):
    """Get user preferences from MongoDB"""
    user_profile = mongo_db.users_profiles.find_one({"_id": user_id})
    if user_profile and "preferences" in user_profile:
        return user_profile["preferences"]
    return None


def get_user_ratings(user_id):
    """Get all ratings for a user"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT isbn, rating FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        return {row[0]: row[1] for row in result.fetchall()}


def get_user_favorite_genres(user_id, min_rating=7, limit=5):
    """Get user's top genres from highly-rated books"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rg.genre_name, COUNT(*) as count
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            JOIN books_subgenres bs ON b.isbn = bs.isbn
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE r.user_id = :user_id AND r.rating >= :min_rating
            GROUP BY rg.genre_name
            ORDER BY count DESC
            LIMIT :limit
        """), {"user_id": user_id, "min_rating": min_rating, "limit": limit})
        return [row[0] for row in result.fetchall()]


def content_based_score(book_meta, user_prefs, user_genres):
    """Calculate content-based score using genres, authors, price"""
    score = 0.0
    reasons = []
    
    if not book_meta:
        return 0.0, []
    
    # Genre matching
    if user_genres and "genres" in book_meta:
        book_genres = book_meta.get("genres", [])
        genre_matches = len(set(user_genres).intersection(set(book_genres)))
        if genre_matches > 0:
            genre_score = genre_matches * 10
            score += genre_score
            reasons.append(f"genre match (+{genre_score})")
    
    # Author matching
    if user_prefs and "top_authors" in user_prefs:
        book_authors = book_meta.get("authors", "")
        for fav_author in user_prefs["top_authors"][:3]:
            if fav_author.lower() in book_authors.lower():
                score += 8
                reasons.append(f"favorite author: {fav_author}")
                break
    
    # Price matching
    if user_prefs and "avg_price" in user_prefs:
        user_price = user_prefs["avg_price"]
        if "price" in book_meta and book_meta["price"]:
            book_price = book_meta["price"]
            price_diff = abs(book_price - user_price)
            if price_diff <= 5:
                score += 3
                reasons.append("price match")
    
    return score, reasons


def collaborative_score(isbn, similar_users):
    """Calculate collaborative score from similar users"""
    score = 0.0
    raters = []
    
    for similar_user in similar_users:
        user_id = similar_user["user_id"]
        similarity = similar_user["correlation"]
        
        with mysql_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT rating FROM ratings
                WHERE user_id = :user_id AND isbn = :isbn
            """), {"user_id": user_id, "isbn": isbn})
            row = result.fetchone()
            
            if row:
                rating = row[0]
                if rating >= 7:
                    weighted_score = rating * similarity
                    score += weighted_score
                    raters.append((user_id, rating))
    
    return score, raters


def popularity_score(book_meta):
    """Calculate popularity score from rating metrics"""
    if not book_meta or "rating_metrics" not in book_meta:
        return 0.0
    
    metrics = book_meta["rating_metrics"]
    
    # Use rating_score (Bayesian average)
    rating_score = metrics.get("rating_score", 0)
    
    # Boost by number of ratings (logarithmic scale)
    r_count = metrics.get("r_count", 0)
    count_boost = math.log(max(r_count, 1)) * 0.5
    
    return rating_score + count_boost


def find_similar_users_simple(target_user_id, min_common_books=5, limit=20):
    """Simplified similar user finding"""
    target_ratings = get_user_ratings(target_user_id)
    
    if not target_ratings:
        return []
    
    target_books = set(target_ratings.keys())
    
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT user_id
            FROM ratings
            WHERE isbn IN :isbns AND user_id != :target_user_id
        """), {"isbns": tuple(target_books), "target_user_id": target_user_id})
        
        candidate_users = [row[0] for row in result.fetchall()]
    
    similar_users = []
    for candidate_id in candidate_users[:300]:
        candidate_ratings = get_user_ratings(candidate_id)
        common_books = target_books.intersection(set(candidate_ratings.keys()))
        
        if len(common_books) >= min_common_books:
            # Simple correlation calculation
            target_vals = [target_ratings[isbn] for isbn in common_books]
            candidate_vals = [candidate_ratings[isbn] for isbn in common_books]
            
            target_mean = sum(target_vals) / len(target_vals)
            candidate_mean = sum(candidate_vals) / len(candidate_vals)
            
            target_centered = [r - target_mean for r in target_vals]
            candidate_centered = [r - candidate_mean for r in candidate_vals]
            
            numerator = sum(t * c for t, c in zip(target_centered, candidate_centered))
            target_sq = sum(t * t for t in target_centered)
            candidate_sq = sum(c * c for c in candidate_centered)
            
            if target_sq > 0 and candidate_sq > 0:
                denominator = math.sqrt(target_sq * candidate_sq)
                correlation = numerator / denominator
                
                if correlation > 0.3:
                    similar_users.append({
                        "user_id": candidate_id,
                        "correlation": correlation
                    })
    
    similar_users.sort(key=lambda x: x["correlation"], reverse=True)
    return similar_users[:limit]


def get_hybrid_recommendations(user_id, limit=10, content_weight=0.4, 
                               collab_weight=0.4, popularity_weight=0.2):
    """Get recommendations using hybrid scoring"""
    
    # Get user data
    user_prefs = get_user_preferences(user_id)
    user_genres = get_user_favorite_genres(user_id)
    user_ratings = get_user_ratings(user_id)
    rated_isbns = set(user_ratings.keys())
    
    # Find similar users for collaborative filtering
    similar_users = find_similar_users_simple(user_id)
    
    # Get candidate books (from user preferences and similar users)
    candidate_isbns = set()
    
    # Candidates from user's favorite genres
    if user_genres:
        with mysql_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT DISTINCT b.isbn
                FROM books b
                JOIN books_subgenres bs ON b.isbn = bs.isbn
                JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
                JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
                WHERE rg.genre_name IN :genres
                LIMIT 500
            """), {"genres": tuple(user_genres)})
            candidate_isbns.update(row[0] for row in result.fetchall())
    
    # Candidates from similar users
    for similar_user in similar_users[:10]:
        sim_ratings = get_user_ratings(similar_user["user_id"])
        for isbn, rating in sim_ratings.items():
            if rating >= 7:
                candidate_isbns.add(isbn)
    
    # Remove already rated books
    candidate_isbns -= rated_isbns
    
    # Score each candidate
    scored_books = []
    for isbn in list(candidate_isbns)[:1000]:  # Limit for performance
        book_meta = mongo_db.books_metadata.find_one({"_id": isbn})
        
        if not book_meta:
            continue
        
        # Calculate component scores
        content_sc, content_reasons = content_based_score(book_meta, user_prefs, user_genres)
        collab_sc, collab_raters = collaborative_score(isbn, similar_users)
        pop_sc = popularity_score(book_meta)
        
        # Weighted hybrid score
        total_score = (content_sc * content_weight + 
                      collab_sc * collab_weight + 
                      pop_sc * popularity_weight)
        
        scored_books.append({
            "isbn": isbn,
            "total_score": total_score,
            "content_score": content_sc,
            "collab_score": collab_sc,
            "popularity_score": pop_sc,
            "content_reasons": content_reasons,
            "collab_raters": len(collab_raters),
            "metadata": book_meta
        })
    
    # Sort by total score
    scored_books.sort(key=lambda x: x["total_score"], reverse=True)
    return scored_books[:limit]


def enrich_recommendations(recommendations):
    """Add book details from MySQL"""
    enriched = []
    
    for rec in recommendations:
        isbn = rec["isbn"]
        
        with mysql_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT title, authors, publisher, publication_year
                FROM books WHERE isbn = :isbn
            """), {"isbn": isbn})
            book_row = result.fetchone()
        
        if not book_row:
            continue
        
        title, authors, publisher, pub_year = book_row
        
        enriched.append({
            **rec,
            "title": title,
            "authors": authors,
            "publisher": publisher,
            "publication_year": pub_year
        })
    
    return enriched


def display_recommendations(recommendations, weights):
    """Display hybrid recommendations"""
    print("\n" + "=" * 80)
    print("🎯 HYBRID RECOMMENDATIONS")
    print("=" * 80)
    print(f"\nWeights: Content={weights[0]:.1%}, Collaborative={weights[1]:.1%}, "
          f"Popularity={weights[2]:.1%}")
    
    print("\n" + "=" * 80)
    print("📚 RECOMMENDED BOOKS")
    print("=" * 80)
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['title']}")
        print(f"   ISBN: {rec['isbn']}")
        print(f"   Authors: {rec['authors']}")
        print(f"   Total Score: {rec['total_score']:.2f}")
        print(f"   Component Scores:")
        print(f"     • Content: {rec['content_score']:.2f} - {', '.join(rec['content_reasons']) if rec['content_reasons'] else 'N/A'}")
        print(f"     • Collaborative: {rec['collab_score']:.2f} - {rec['collab_raters']} similar users")
        print(f"     • Popularity: {rec['popularity_score']:.2f}")
        
        if 'rating_metrics' in rec['metadata']:
            rm = rec['metadata']['rating_metrics']
            print(f"   Global: {rm.get('r_avg', 'N/A')}/10 ({rm.get('r_count', 0)} ratings)")


def main():
    parser = argparse.ArgumentParser(description="Hybrid recommendation system")
    parser.add_argument("--user_id", type=int, required=True, help="User ID")
    parser.add_argument("--limit", type=int, default=10, help="Number of recommendations")
    parser.add_argument("--content_weight", type=float, default=0.4, help="Content-based weight")
    parser.add_argument("--collab_weight", type=float, default=0.4, help="Collaborative weight")
    parser.add_argument("--popularity_weight", type=float, default=0.2, help="Popularity weight")
    
    args = parser.parse_args()
    
    # Normalize weights
    total_weight = args.content_weight + args.collab_weight + args.popularity_weight
    content_w = args.content_weight / total_weight
    collab_w = args.collab_weight / total_weight
    pop_w = args.popularity_weight / total_weight
    
    try:
        print(f"\n🔍 Generating hybrid recommendations for User {args.user_id}...")
        
        recommendations = get_hybrid_recommendations(
            args.user_id, 
            limit=args.limit,
            content_weight=content_w,
            collab_weight=collab_w,
            popularity_weight=pop_w
        )
        
        if not recommendations:
            print("\n⚠️  No recommendations found")
            return
        
        enriched = enrich_recommendations(recommendations)
        display_recommendations(enriched, (content_w, collab_w, pop_w))
    
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
