"""
Insert New Data Script: Add users, books, and ratings with automatic metric updates
Demonstrates how to maintain consistency across MySQL and MongoDB when adding new data.
"""

from pathlib import Path
import sys
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# Database configurations
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

# Connect to databases
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


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_next_user_id():
    """Get next available user_id"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(user_id) as max_id FROM users"))
        max_id = result.fetchone()[0]
        return (max_id or 0) + 1


def insert_new_user(age, age_group, gender, location, country, latitude=None, longitude=None):
    """Insert a new user into MySQL and MongoDB"""
    user_id = get_next_user_id()
    
    # Insert into MySQL
    with mysql_engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO users (user_id, age, age_group, gender, location, country, 
                             loc_latitude, loc_longitude, has_ratings, has_preferences)
            VALUES (:user_id, :age, :age_group, :gender, :location, :country, 
                    :lat, :lon, FALSE, FALSE)
        """), {
            "user_id": user_id,
            "age": age,
            "age_group": age_group,
            "gender": gender,
            "location": location,
            "country": country,
            "lat": latitude,
            "lon": longitude
        })
        conn.commit()
    
    # Insert into MongoDB (minimal profile initially)
    mongo_db.users_profiles.insert_one({
        "_id": user_id,
        "profile": {
            "reader_level": "new_reader",
            "has_ratings": False,
            "has_preferences": False,
            "total_ratings": 0,
            "total_books": 0
        }
    })
    
    print(f"✅ Inserted new user {user_id}: {age_group}, {gender}, {country}")
    return user_id


def insert_new_book(isbn, title, authors, publication_year=None, publisher=None, 
                   price_usd=None, genre=None, root_genre_ids=None, subgenre_ids=None):
    """Insert a new book into MySQL and MongoDB"""
    
    # Insert into MySQL
    with mysql_engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO books (isbn, title, authors, publication_year, publisher, genre)
            VALUES (:isbn, :title, :authors, :year, :publisher, :genre)
        """), {
            "isbn": isbn,
            "title": title,
            "authors": str(authors) if isinstance(authors, list) else authors,
            "year": publication_year,
            "publisher": publisher,
            "genre": genre
        })
        
        # Insert genre relationships
        if root_genre_ids:
            for root_id in root_genre_ids:
                conn.execute(text("""
                    INSERT INTO book_root_genres (isbn, root_id) VALUES (:isbn, :root_id)
                """), {"isbn": isbn, "root_id": root_id})
        
        if subgenre_ids:
            for subgenre_id in subgenre_ids:
                conn.execute(text("""
                    INSERT INTO book_subgenres (isbn, subgenre_id) VALUES (:isbn, :subgenre_id)
                """), {"isbn": isbn, "subgenre_id": subgenre_id})
        
        conn.commit()
    
    # Insert into MongoDB with initial metrics
    mongo_doc = {
        "_id": isbn,
        "extra_metadata": {},
        "rating_metrics": {
            "r_total": 0,
            "r_count": 0,
            "r_avg": 0.0,
            "rating_score": 0.0,
            "r_category": "unrated"
        },
        "popularity_metrics": {
            "recent_count": 0,
            "popularity": 0.0,
            "popularity_cat": "unknown"
        }
    }
    
    if price_usd is not None:
        mongo_doc["extra_metadata"]["price_usd"] = float(price_usd)
    if genre:
        mongo_doc["extra_metadata"]["genre"] = genre
    
    mongo_db.books_metadata.insert_one(mongo_doc)
    
    print(f"✅ Inserted new book {isbn}: {title}")
    return isbn


def insert_rating_and_update_metrics(user_id, isbn, rating):
    """Insert a rating and update all derived metrics in MySQL and MongoDB"""
    
    # Determine rating category
    if rating == 0:
        r_cat = "not_rated"
    elif rating <= 3:
        r_cat = "low"
    elif rating <= 6:
        r_cat = "mid"
    elif rating <= 8:
        r_cat = "high"
    else:
        r_cat = "very_high"
    
    # Get sequence numbers
    with mysql_engine.connect() as conn:
        # Get r_seq_user
        result = conn.execute(text("""
            SELECT COALESCE(MAX(r_seq_user), 0) + 1 as next_seq
            FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        r_seq_user = result.fetchone()[0]
        
        # Get r_seq_book
        result = conn.execute(text("""
            SELECT COALESCE(MAX(r_seq_book), 0) + 1 as next_seq
            FROM ratings WHERE isbn = :isbn
        """), {"isbn": isbn})
        r_seq_book = result.fetchone()[0]
        
        # Insert rating
        conn.execute(text("""
            INSERT INTO ratings (user_id, isbn, rating, r_seq_user, r_seq_book, r_cat)
            VALUES (:user_id, :isbn, :rating, :r_seq_user, :r_seq_book, :r_cat)
        """), {
            "user_id": user_id,
            "isbn": isbn,
            "rating": rating,
            "r_seq_user": r_seq_user,
            "r_seq_book": r_seq_book,
            "r_cat": r_cat
        })
        conn.commit()
    
    # Update book metrics in MongoDB
    update_book_metrics(isbn)
    
    # Update user metrics in MongoDB
    update_user_metrics(user_id)
    
    # Update user flags in MySQL
    with mysql_engine.connect() as conn:
        conn.execute(text("""
            UPDATE users SET has_ratings = TRUE WHERE user_id = :user_id
        """), {"user_id": user_id})
        conn.commit()
    
    print(f"✅ Added rating: User {user_id} rated book {isbn} with {rating}/10")


def update_book_metrics(isbn):
    """Recalculate and update book rating metrics in MongoDB"""
    
    # Get all ratings for this book from MySQL
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rating, COUNT(*) as count
            FROM ratings
            WHERE isbn = :isbn
            GROUP BY rating
        """), {"isbn": isbn})
        ratings_dist = result.fetchall()
    
    if not ratings_dist:
        return
    
    # Calculate metrics
    total_ratings = sum(count for _, count in ratings_dist)
    total_score = sum(rating * count for rating, count in ratings_dist)
    avg_rating = total_score / total_ratings if total_ratings > 0 else 0
    
    # Calculate standard deviation
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rating FROM ratings WHERE isbn = :isbn
        """), {"isbn": isbn})
        all_ratings = [r[0] for r in result.fetchall()]
    
    std_rating = float(np.std(all_ratings)) if len(all_ratings) > 1 else 0.0
    
    # Determine category
    if avg_rating == 0:
        r_category = "unrated"
    elif avg_rating <= 3:
        r_category = "low"
    elif avg_rating <= 6:
        r_category = "mid"
    elif avg_rating <= 8:
        r_category = "high"
    else:
        r_category = "very_high"
    
    # Calculate rating score (weighted)
    rating_score = (total_score + 5 * 5) / (total_ratings + 5)  # Bayesian average
    
    # Update MongoDB
    mongo_db.books_metadata.update_one(
        {"_id": isbn},
        {"$set": {
            "rating_metrics.r_total": int(total_score),
            "rating_metrics.r_count": int(total_ratings),
            "rating_metrics.r_avg": round(float(avg_rating), 2),
            "rating_metrics.r_std": round(std_rating, 2),
            "rating_metrics.rating_score": round(float(rating_score), 2),
            "rating_metrics.r_category": r_category
        }}
    )
    
    print(f"   📊 Updated book {isbn} metrics: {total_ratings} ratings, avg={avg_rating:.2f}")


def update_user_metrics(user_id):
    """Recalculate and update user profile metrics in MongoDB"""
    
    # Get user ratings from MySQL
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rating, COUNT(DISTINCT isbn) as book_count
            FROM ratings
            WHERE user_id = :user_id
            GROUP BY rating
        """), {"user_id": user_id})
        ratings_data = result.fetchall()
        
        result = conn.execute(text("""
            SELECT COUNT(*) as total, COUNT(DISTINCT isbn) as books,
                   SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END) as explicit_count
            FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        totals = result.fetchone()
    
    total_ratings = totals[0]
    total_books = totals[1]
    explicit_ratings = totals[2]
    
    if total_ratings == 0:
        return
    
    # Get all ratings for statistics
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rating FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        all_ratings = [r[0] for r in result.fetchall()]
    
    mean_rating = float(np.mean(all_ratings))
    median_rating = float(np.median(all_ratings))
    std_rating = float(np.std(all_ratings)) if len(all_ratings) > 1 else 0.0
    
    # Determine reader level
    if explicit_ratings == 0:
        reader_level = "implicit_only"
    elif explicit_ratings < 10:
        reader_level = "new_reader"
    elif explicit_ratings < 50:
        reader_level = "casual_reader"
    elif explicit_ratings < 200:
        reader_level = "active_reader"
    else:
        reader_level = "power_reader"
    
    # Determine critic profile based on rating distribution
    explicit_only = [r for r in all_ratings if r > 0]
    if explicit_only:
        mean_explicit = np.mean(explicit_only)
        std_explicit = np.std(explicit_only) if len(explicit_only) > 1 else 0
        
        if std_explicit < 1.5:
            critic_profile = "consistent"
        elif mean_explicit < 5:
            critic_profile = "critical"
        elif mean_explicit > 7:
            critic_profile = "generous"
        else:
            critic_profile = "balanced"
    else:
        critic_profile = "unknown"
    
    # Update MongoDB
    mongo_db.users_profiles.update_one(
        {"_id": user_id},
        {"$set": {
            "profile.reader_level": reader_level,
            "profile.critic_profile": critic_profile,
            "profile.mean_rating": round(mean_rating, 2),
            "profile.median_rating": round(median_rating, 2),
            "profile.std_rating": round(std_rating, 2),
            "profile.total_ratings": int(total_ratings),
            "profile.total_books": int(total_books),
            "profile.explicit_ratings": int(explicit_ratings),
            "profile.has_ratings": True
        }}
    )
    
    print(f"   📊 Updated user {user_id} metrics: {total_ratings} ratings, {reader_level}, {critic_profile}")


# ============================================================================
# EXAMPLE INSERTIONS
# ============================================================================

def demo_insertions():
    """Demonstrate inserting new users, books, and ratings"""
    
    print("=" * 80)
    print("📝 DEMONSTRATION: Inserting New Data with Metric Updates")
    print("=" * 80 + "\n")
    
    # 1. Insert a new user
    print("1️⃣  Inserting new user...")
    new_user_id = insert_new_user(
        age=25,
        age_group="young_adult_18_24",
        gender="female",
        location="Seattle, WA, USA",
        country="USA",
        latitude=47.6062,
        longitude=-122.3321
    )
    print()
    
    # 2. Insert a new book
    print("2️⃣  Inserting new book...")
    new_isbn = "9999999999"  # Use a unique ISBN
    new_book_isbn = insert_new_book(
        isbn=new_isbn,
        title="Introduction to Database Systems",
        authors="['John Doe', 'Jane Smith']",
        publication_year=2024,
        publisher="Tech Books Publishing",
        price_usd=49.99,
        genre="Computer Science",
        root_genre_ids=[1],  # Assuming 1 is a valid root_genre_id
        subgenre_ids=[5]     # Assuming 5 is a valid subgenre_id
    )
    print()
    
    # 3. Add ratings for the new user and book
    print("3️⃣  Adding ratings and updating metrics...")
    
    # Get some existing books to rate
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT isbn FROM books LIMIT 5
        """))
        existing_books = [row[0] for row in result.fetchall()]
    
    # New user rates existing books
    ratings_to_add = [
        (new_user_id, existing_books[0], 8),
        (new_user_id, existing_books[1], 9),
        (new_user_id, existing_books[2], 7),
    ]
    
    for user_id, isbn, rating in ratings_to_add:
        insert_rating_and_update_metrics(user_id, isbn, rating)
    
    # Existing users rate the new book
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT user_id FROM users WHERE has_ratings = TRUE LIMIT 3
        """))
        existing_users = [row[0] for row in result.fetchall()]
    
    for user_id in existing_users:
        insert_rating_and_update_metrics(user_id, new_book_isbn, 8)
    
    print()
    print("=" * 80)
    print("✅ DEMONSTRATION COMPLETE")
    print("=" * 80)
    print(f"\nCreated:")
    print(f"  • User ID: {new_user_id}")
    print(f"  • Book ISBN: {new_book_isbn}")
    print(f"  • Total new ratings: {len(ratings_to_add) + len(existing_users)}")
    print(f"\nAll metrics automatically updated in MySQL and MongoDB!")


if __name__ == "__main__":
    try:
        demo_insertions()
    finally:
        mongo_client.close()
