"""
Smart Recommendation System
Intelligently selects the best recommendation strategy based on available user data.
- Has Ratings -> Hybrid (Collaborative + Content)
- Has Preferences -> Preference-Based (Onboarding)
- Has Location -> Geographic
- New User -> Cold Start (Demographics/Trending)
"""

from sqlalchemy import text
import random
from .recommendation_hybrid import get_hybrid_recommendations
from .recommendation_cold_start import get_cold_start_recommendations
from .recommendation_geographic import get_geographic_recommendations
from .recommendation_trending import get_trending_recommendations

def get_user_status(mysql_engine, user_id):
    """Check user flags: has_ratings, has_preferences, has_location"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT has_ratings, has_preferences, 
                   (loc_latitude IS NOT NULL AND loc_longitude IS NOT NULL) as has_location
            FROM users WHERE user_id = :uid
        """), {"uid": user_id}).fetchone()
        
        if result:
            return {
                "has_ratings": bool(result[0]),
                "has_preferences": bool(result[1]),
                "has_location": bool(result[2])
            }
    return None

def get_preference_based_recommendations(mysql_engine, mongo_db, user_id, limit=10):
    """
    Generate recommendations based purely on explicit preferences (onboarding data).
    Used when a user has no ratings but has filled out their profile preferences.
    """
    # 1. Get preferences from MongoDB
    user_profile = mongo_db.users_profiles.find_one({"_id": user_id})
    if not user_profile or "preferences" not in user_profile:
        return []
    
    prefs = user_profile["preferences"]
    pref_genres = prefs.get("pref_root_genres", [])
    pref_authors = prefs.get("pref_authors", [])
    
    if isinstance(pref_genres, str):
        pref_genres = [pref_genres]
    if isinstance(pref_authors, str):
        pref_authors = [pref_authors]
        
    print(f"   Found preferences: Genres={pref_genres}, Authors={pref_authors}")
    
    recommendations = []
    seen_isbns = set()
    
    with mysql_engine.connect() as conn:
        # Strategy A: Find books by preferred authors
        if pref_authors:
            for author in pref_authors:
                # Simple LIKE query for author
                q = text("""
                    SELECT isbn, title, authors, publication_year 
                    FROM books 
                    WHERE authors LIKE :author 
                    LIMIT 5
                """)
                results = conn.execute(q, {"author": f"%{author}%"}).fetchall()
                for row in results:
                    if row[0] not in seen_isbns:
                        recommendations.append({
                            "isbn": row[0],
                            "title": row[1],
                            "authors": row[2],
                            "year": row[3],
                            "score": 10.0, # High score for direct author match
                            "reason": f"Preferred Author: {author}"
                        })
                        seen_isbns.add(row[0])
        
        # Strategy B: Find books in preferred genres
        if pref_genres and len(recommendations) < limit:
            for genre in pref_genres:
                q = text("""
                    SELECT b.isbn, b.title, b.authors, b.publication_year
                    FROM books b
                    JOIN book_root_genres brg ON b.isbn = brg.isbn
                    JOIN root_genres rg ON brg.root_id = rg.root_id
                    WHERE rg.root_name = :genre
                    ORDER BY b.publication_year DESC -- Prefer newer books
                    LIMIT 10
                """)
                results = conn.execute(q, {"genre": genre}).fetchall()
                for row in results:
                    if row[0] not in seen_isbns:
                        recommendations.append({
                            "isbn": row[0],
                            "title": row[1],
                            "authors": row[2],
                            "year": row[3],
                            "score": 5.0, # Medium score for genre match
                            "reason": f"Preferred Genre: {genre}"
                        })
                        seen_isbns.add(row[0])
                        
    # Sort by score and return top N
    recommendations.sort(key=lambda x: x['score'], reverse=True)
    return recommendations[:limit]

def get_smart_recommendations(mysql_engine, mongo_db, user_id, limit=10):
    """
    Main entry point for smart recommendations.
    Dispatches to the appropriate strategy based on user data.
    """
    status = get_user_status(mysql_engine, user_id)
    
    if not status:
        print(f"⚠️ User {user_id} not found.")
        return []
        
    print(f"🧠 Smart Strategy Analysis for User {user_id}:")
    print(f"   Ratings: {status['has_ratings']} | Preferences: {status['has_preferences']} | Location: {status['has_location']}")
    
    # Priority 1: Hybrid (Best if we have ratings)
    if status['has_ratings']:
        print("-> Selected Strategy: HYBRID (Collaborative + Content)")
        return get_hybrid_recommendations(mysql_engine, mongo_db, user_id, limit)
        
    # Priority 2: Preferences (Onboarding data)
    elif status['has_preferences']:
        print("-> Selected Strategy: PREFERENCE-BASED (Onboarding)")
        recs = get_preference_based_recommendations(mysql_engine, mongo_db, user_id, limit)
        if recs:
            return recs
        print("   (Preferences yielded no results, falling back...)")
        
    # Priority 3: Geographic (If we know where they are)
    if status['has_location']:
        print("-> Selected Strategy: GEOGRAPHIC (Location-based)")
        recs = get_geographic_recommendations(mysql_engine, user_id, limit, mongo_db=mongo_db)
        if recs:
            return recs
            
    # Priority 4: Cold Start / Trending (Fallback)
    print("-> Selected Strategy: COLD START (Demographics/Trending)")
    return get_cold_start_recommendations(mysql_engine, mongo_db, user_id, limit)
