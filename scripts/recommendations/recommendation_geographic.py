"""
Geographic-Based Recommendation System
Recommends books popular in user's geographic region.
Uses location clustering to find regional reading preferences.
"""

from sqlalchemy import text
import math

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


def get_user_location(mysql_engine, user_id):
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


def find_nearby_users(mysql_engine, user_id, radius_km=100, limit=500):
    """Find users within specified radius"""
    user_loc = get_user_location(mysql_engine, user_id)
    
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


def get_regional_favorites(mysql_engine, nearby_users, min_rating=7, limit=50):
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


def filter_already_rated(mysql_engine, favorites, user_id):
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


