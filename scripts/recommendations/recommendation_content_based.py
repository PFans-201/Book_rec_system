"""
Content-Based Recommendation System
Recommends books similar to what the user has rated highly, based on:
- Genre overlap
- Author familiarity
- Price preferences
- Publication year preferences
"""

from pathlib import Path
import sys
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import argparse
from collections import Counter

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# Database setup
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
    user_prof = mongo_db.users_profiles.find_one({"_id": user_id})
    if not user_prof or "preferences" not in user_prof:
        return None
    return user_prof["preferences"]


def get_user_highly_rated_books(user_id, min_rating=7):
    """Get books the user rated highly"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT r.isbn, r.rating, b.authors
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            WHERE r.user_id = :user_id AND r.rating >= :min_rating
        """), {"user_id": user_id, "min_rating": min_rating})
        return result.fetchall()


def get_user_favorite_genres(user_id, limit=5):
    """Get user's most rated genres"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rg.root_name, COUNT(*) as cnt
            FROM ratings r
            JOIN book_root_genres brg ON r.isbn = brg.isbn
            JOIN root_genres rg ON brg.root_id = rg.root_id
            WHERE r.user_id = :user_id AND r.rating >= 7
            GROUP BY rg.root_name
            ORDER BY cnt DESC
            LIMIT :limit
        """), {"user_id": user_id, "limit": limit})
        return [row[0] for row in result.fetchall()]


def get_user_favorite_authors(user_id, limit=5):
    """Extract favorite authors from highly rated books"""
    highly_rated = get_user_highly_rated_books(user_id)
    all_authors = []
    
    for _, _, authors_str in highly_rated:
        if authors_str:
            try:
                author_list = eval(authors_str) if authors_str.startswith('[') else [authors_str]
                all_authors.extend(author_list)
            except:
                pass
    
    author_counts = Counter(all_authors)
    return [author for author, _ in author_counts.most_common(limit)]


def find_similar_books(user_id, limit=10, exclude_rated=True):
    """Find books similar to user's preferences"""
    
    # Get user profile
    prefs = get_user_preferences(user_id)
    fav_genres = get_user_favorite_genres(user_id)
    fav_authors = get_user_favorite_authors(user_id)
    
    print(f"\n🎯 Finding content-based recommendations for User {user_id}")
    print(f"Favorite genres: {fav_genres}")
    print(f"Favorite authors: {fav_authors[:3]}")
    
    # Get books the user has already rated (to exclude)
    rated_isbns = set()
    if exclude_rated:
        with mysql_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT isbn FROM ratings WHERE user_id = :user_id
            """), {"user_id": user_id})
            rated_isbns = {row[0] for row in result.fetchall()}
    
    # Find candidate books matching genres
    candidates = []
    
    with mysql_engine.connect() as conn:
        for genre in fav_genres:
            result = conn.execute(text("""
                SELECT DISTINCT b.isbn, b.title, b.authors, b.publisher
                FROM books b
                JOIN book_root_genres brg ON b.isbn = brg.isbn
                JOIN root_genres rg ON brg.root_id = rg.root_id
                WHERE rg.root_name = :genre
                LIMIT 100
            """), {"genre": genre})
            
            for row in result.fetchall():
                isbn, title, authors_str, publisher = row
                if isbn not in rated_isbns:
                    candidates.append({
                        "isbn": isbn,
                        "title": title,
                        "authors": authors_str,
                        "publisher": publisher,
                        "genre_match": genre
                    })
    
    # Score each candidate
    scored_books = []
    
    for candidate in candidates:
        score = 0.0
        reasons = []
        
        # Genre match (already filtered)
        score += 10.0
        reasons.append(f"Genre: {candidate['genre_match']}")
        
        # Author match
        if candidate["authors"]:
            try:
                candidate_authors = eval(candidate["authors"]) if candidate["authors"].startswith('[') else [candidate["authors"]]
                for author in fav_authors:
                    if any(author.lower() in ca.lower() for ca in candidate_authors):
                        score += 5.0
                        reasons.append(f"Author: {author}")
                        break
            except:
                pass
        
        # Get MongoDB data
        book_meta = mongo_db.books_metadata.find_one({"_id": candidate["isbn"]})
        
        if book_meta:
            # Rating quality
            if "rating_metrics" in book_meta:
                rm = book_meta["rating_metrics"]
                avg_rating = rm.get("r_avg", 0)
                rating_count = rm.get("r_count", 0)
                
                if avg_rating >= 7:
                    score += avg_rating * 2
                    reasons.append(f"High rating: {avg_rating}/10")
                
                if rating_count >= 10:
                    score += min(rating_count / 10, 5)
                    reasons.append(f"Well-reviewed: {rating_count} ratings")
            
            # Price match
            if prefs and "extra_metadata" in book_meta:
                price = book_meta["extra_metadata"].get("price_usd")
                if price:
                    pref_min = prefs.get("pref_price_min")
                    pref_max = prefs.get("pref_price_max")
                    if pref_min and pref_max:
                        if pref_min <= price <= pref_max * 1.2:  # Allow 20% over max
                            score += 3.0
                            reasons.append(f"Price fit: ${price:.2f}")
        
        scored_books.append({
            **candidate,
            "score": score,
            "reasons": reasons,
            "metadata": book_meta
        })
    
    # Sort by score and return top N
    scored_books.sort(key=lambda x: x["score"], reverse=True)
    return scored_books[:limit]


def display_recommendations(recommendations):
    """Display recommendations in a formatted way"""
    print("\n" + "=" * 80)
    print("📚 CONTENT-BASED RECOMMENDATIONS")
    print("=" * 80)
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['title']}")
        print(f"   ISBN: {rec['isbn']}")
        print(f"   Authors: {rec['authors']}")
        print(f"   Score: {rec['score']:.1f}")
        print(f"   Why recommended:")
        for reason in rec['reasons']:
            print(f"     • {reason}")
        
        if rec.get('metadata'):
            meta = rec['metadata']
            if 'rating_metrics' in meta:
                rm = meta['rating_metrics']
                print(f"   Rating: {rm.get('r_avg', 'N/A')}/10 ({rm.get('r_count', 0)} ratings)")
            if 'extra_metadata' in meta:
                price = meta['extra_metadata'].get('price_usd')
                if price:
                    print(f"   Price: ${price:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Content-based book recommendations")
    parser.add_argument("--user_id", type=int, required=True, help="User ID")
    parser.add_argument("--limit", type=int, default=10, help="Number of recommendations")
    parser.add_argument("--include_rated", action="store_true", help="Include already rated books")
    
    args = parser.parse_args()
    
    try:
        recommendations = find_similar_books(
            args.user_id,
            limit=args.limit,
            exclude_rated=not args.include_rated
        )
        
        if not recommendations:
            print(f"\n⚠️  No recommendations found for user {args.user_id}")
            print("User may be new or have unusual preferences.")
        else:
            display_recommendations(recommendations)
    
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
