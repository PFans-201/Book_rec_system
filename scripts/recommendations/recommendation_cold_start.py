"""
Cold-Start Recommendation System
Provides recommendations for new users with few or no ratings.
Uses demographic information and global popularity.
"""

from pathlib import Path
import sys
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import argparse

# Setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
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


def get_user_demographics(user_id):
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


def get_user_rating_count(user_id):
    """Check if user is truly cold-start"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        count = result.fetchone()[0]
        return count if count else 0


def find_similar_demographic_users(demographics, limit=100):
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
        
        return similar


def get_demographic_favorites(similar_users, min_rating=7, limit=100):
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


def boost_with_global_popularity(favorites, popularity_weight=0.3):
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


def enrich_recommendations(recommendations):
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


def display_recommendations(demographics, rating_count, similar_user_count, recommendations):
    """Display cold-start recommendations"""
    print("\n" + "=" * 80)
    print("🆕 COLD-START RECOMMENDATIONS")
    print("=" * 80)
    
    print(f"\nUser Profile:")
    print(f"  • Ratings: {rating_count}")
    print(f"  • Age Group: {demographics.get('age_group', 'Unknown')}")
    print(f"  • Gender: {demographics.get('gender', 'Unknown')}")
    print(f"  • Location: {demographics.get('location', 'Unknown')}")
    
    print(f"\nBased on {similar_user_count} users with similar demographics")
    
    print("\n" + "=" * 80)
    print("📚 RECOMMENDED STARTER BOOKS")
    print("=" * 80)
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['title']}")
        print(f"   ISBN: {rec['isbn']}")
        print(f"   Authors: {rec['authors']}")
        print(f"   📊 Recommendation Score: {rec['total_score']:.2f}")
        print(f"   👥 Popular with similar users:")
        print(f"      • {rec['demographic_count']} similar users rated this")
        print(f"      • Average rating from similar users: {rec['demographic_avg']:.1f}/10")
        
        if rec.get('global_rating_score'):
            print(f"   🌐 Global Quality Score: {rec['global_rating_score']:.2f}")
        
        # Show global metrics
        if rec.get('metadata') and 'rating_metrics' in rec['metadata']:
            rm = rec['metadata']['rating_metrics']
            print(f"   Overall: {rm.get('r_avg', 'N/A')}/10 ({rm.get('r_count', 0)} total ratings)")


def main():
    parser = argparse.ArgumentParser(description="Cold-start recommendations for new users")
    parser.add_argument("--user_id", type=int, required=True, help="User ID")
    parser.add_argument("--limit", type=int, default=15, help="Number of recommendations")
    parser.add_argument("--popularity_weight", type=float, default=0.3, 
                       help="Weight for global popularity (0-1)")
    
    args = parser.parse_args()
    
    try:
        print(f"\n🔍 Generating cold-start recommendations for User {args.user_id}...")
        
        # Get user demographics
        demographics = get_user_demographics(args.user_id)
        
        if not demographics:
            print(f"\n⚠️  User {args.user_id} not found")
            return
        
        # Check if user is cold-start
        rating_count = get_user_rating_count(args.user_id)
        
        if rating_count > 20:
            print(f"\n⚠️  User has {rating_count} ratings - not a cold-start case")
            print("Consider using personalized recommendation scripts instead")
            return
        
        # Find similar demographic users
        similar_users = find_similar_demographic_users(demographics)
        
        if not similar_users:
            print("\n⚠️  No similar users found")
            return
        
        print(f"\n📊 Found {len(similar_users)} users with similar demographics")
        
        # Get demographic favorites
        favorites = get_demographic_favorites(similar_users)
        
        if not favorites:
            print("\n⚠️  No recommendations found")
            return
        
        # Boost with global popularity
        favorites = boost_with_global_popularity(favorites, args.popularity_weight)
        
        # Limit and enrich
        recommendations = favorites[:args.limit]
        enriched = enrich_recommendations(recommendations)
        
        display_recommendations(demographics, rating_count, len(similar_users), enriched)
    
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
