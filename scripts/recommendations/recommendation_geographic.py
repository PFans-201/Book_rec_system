"""
Geographic-Based Recommendation System
Recommends books popular in user's geographic region.
Uses location clustering to find regional reading preferences.
"""

from pathlib import Path
import sys
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import argparse
import math

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


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in kilometers using Haversine formula"""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


def get_user_location(user_id):
    """Get user's location from MySQL"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT loc_latitude, loc_longitude, location
            FROM users WHERE user_id = :user_id
        """), {"user_id": user_id})
        row = result.fetchone()
        
        if row and row[0] is not None and row[1] is not None:
            return {
                "latitude": float(row[0]),
                "longitude": float(row[1]),
                "location": row[2]
            }
    return None


def find_nearby_users(user_id, radius_km=100, limit=500):
    """Find users within specified radius"""
    user_loc = get_user_location(user_id)
    
    if not user_loc:
        return []
    
    user_lat = user_loc["latitude"]
    user_lon = user_loc["longitude"]
    
    # Get all users with locations
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT user_id, loc_latitude, loc_longitude, location
            FROM users
            WHERE loc_latitude IS NOT NULL 
              AND loc_longitude IS NOT NULL
              AND user_id != :user_id
        """), {"user_id": user_id})
        
        nearby = []
        for row in result.fetchall():
            other_id, lat, lon, location = row
            
            if lat is None or lon is None:
                continue
            
            distance = haversine_distance(user_lat, user_lon, float(lat), float(lon))
            
            if distance <= radius_km:
                nearby.append({
                    "user_id": other_id,
                    "distance": distance,
                    "location": location
                })
        
        # Sort by distance
        nearby.sort(key=lambda x: x["distance"])
        return nearby[:limit]


def get_regional_favorites(nearby_users, min_rating=7, limit=50):
    """Get books highly rated by nearby users"""
    if not nearby_users:
        return []
    
    user_ids = tuple([u["user_id"] for u in nearby_users])
    
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                isbn,
                COUNT(*) as regional_rating_count,
                AVG(rating) as regional_avg_rating,
                SUM(CASE WHEN rating >= 8 THEN 1 ELSE 0 END) as high_rating_count
            FROM ratings
            WHERE user_id IN :user_ids AND rating >= :min_rating
            GROUP BY isbn
            HAVING regional_rating_count >= 3
            ORDER BY high_rating_count DESC, regional_avg_rating DESC
            LIMIT :limit
        """), {
            "user_ids": user_ids,
            "min_rating": min_rating,
            "limit": limit
        })
        
        favorites = []
        for row in result.fetchall():
            isbn, count, avg_rating, high_count = row
            favorites.append({
                "isbn": isbn,
                "regional_rating_count": count,
                "regional_avg_rating": avg_rating,
                "high_rating_count": high_count
            })
        
        return favorites


def filter_already_rated(favorites, user_id):
    """Remove books the user has already rated"""
    if not favorites:
        return []
    
    isbns = tuple([f["isbn"] for f in favorites])
    
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT isbn FROM ratings WHERE user_id = :user_id AND isbn IN :isbns
        """), {"user_id": user_id, "isbns": isbns})
        
        rated_isbns = {row[0] for row in result.fetchall()}
    
    return [f for f in favorites if f["isbn"] not in rated_isbns]


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


def display_recommendations(user_location, nearby_users, recommendations):
    """Display geographic recommendations"""
    print("\n" + "=" * 80)
    print("🌍 GEOGRAPHIC RECOMMENDATIONS")
    print("=" * 80)
    
    if user_location:
        print(f"\nYour Location: {user_location.get('location', 'Unknown')}")
        print(f"Coordinates: {user_location['latitude']:.4f}, {user_location['longitude']:.4f}")
    
    print(f"\nBased on {len(nearby_users)} nearby readers")
    
    if nearby_users:
        print("\nNearest readers:")
        for i, user in enumerate(nearby_users[:3], 1):
            print(f"  {i}. User {user['user_id']} - {user['distance']:.1f} km away ({user.get('location', 'Unknown')})")
    
    print("\n" + "=" * 80)
    print("📚 POPULAR IN YOUR REGION")
    print("=" * 80)
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['title']}")
        print(f"   ISBN: {rec['isbn']}")
        print(f"   Authors: {rec['authors']}")
        print(f"   📍 Regional Popularity:")
        print(f"      • {rec['regional_rating_count']} nearby readers rated this")
        print(f"      • Regional average: {rec['regional_avg_rating']:.1f}/10")
        print(f"      • {rec['high_rating_count']} gave it 8+ rating")
        
        # Show global metrics
        if rec.get('metadata') and 'rating_metrics' in rec['metadata']:
            rm = rec['metadata']['rating_metrics']
            print(f"   🌐 Global: {rm.get('r_avg', 'N/A')}/10 ({rm.get('r_count', 0)} total ratings)")


def main():
    parser = argparse.ArgumentParser(description="Geographic-based recommendations")
    parser.add_argument("--user_id", type=int, required=True, help="User ID")
    parser.add_argument("--radius", type=int, default=100, help="Search radius in kilometers")
    parser.add_argument("--limit", type=int, default=10, help="Number of recommendations")
    parser.add_argument("--min_rating", type=int, default=7, help="Minimum rating threshold")
    
    args = parser.parse_args()
    
    try:
        print(f"\n🔍 Finding recommendations for User {args.user_id} based on geographic location...")
        
        # Get user location
        user_location = get_user_location(args.user_id)
        
        if not user_location:
            print(f"\n⚠️  User {args.user_id} has no location data")
            print("Cannot provide geographic recommendations")
            return
        
        # Find nearby users
        nearby_users = find_nearby_users(args.user_id, radius_km=args.radius)
        
        if not nearby_users:
            print(f"\n⚠️  No nearby users found within {args.radius} km")
            return
        
        print(f"\n📊 Found {len(nearby_users)} nearby readers")
        
        # Get regional favorites
        favorites = get_regional_favorites(nearby_users, min_rating=args.min_rating)
        
        if not favorites:
            print("\n⚠️  No popular books found in your region")
            return
        
        # Filter already rated
        recommendations = filter_already_rated(favorites, args.user_id)
        
        if not recommendations:
            print("\n⚠️  You've already rated all popular books in your region!")
            return
        
        # Limit and enrich
        recommendations = recommendations[:args.limit]
        enriched = enrich_recommendations(recommendations)
        
        display_recommendations(user_location, nearby_users, enriched)
    
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
