"""
Update Ratings and Preferences Script
Demonstrates adding ratings for users/books without ratings and updating user preferences
to observe the impact on recommendation quality.
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
from collections import Counter
import json

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
# FIND USERS AND BOOKS WITHOUT RATINGS
# ============================================================================

def find_users_without_ratings(limit=10):
    """Find users who have no ratings yet"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT user_id, age_group, gender, country
            FROM users
            WHERE has_ratings = FALSE
            LIMIT :limit
        """), {"limit": limit})
        return result.fetchall()


def find_books_without_ratings(limit=10):
    """Find books that have not been rated yet"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT b.isbn, b.title, b.authors, b.publisher
            FROM books b
            LEFT JOIN ratings r ON b.isbn = r.isbn
            WHERE r.isbn IS NULL
            LIMIT :limit
        """), {"limit": limit})
        return result.fetchall()


def add_ratings_for_inactive_users():
    """Add ratings for users who haven't rated anything yet"""
    print("=" * 80)
    print("📝 Adding Ratings for Users Without Ratings")
    print("=" * 80 + "\n")
    
    users = find_users_without_ratings(limit=5)
    
    if not users:
        print("No users without ratings found!")
        return
    
    # Get some popular books
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT isbn, title FROM books
            WHERE isbn IN (
                SELECT isbn FROM ratings
                GROUP BY isbn
                ORDER BY COUNT(*) DESC
                LIMIT 20
            )
        """))
        popular_books = result.fetchall()
    
    for user in users:
        user_id, age_group, gender, country = user
        print(f"User {user_id} ({age_group}, {gender}, {country}):")
        
        # Randomly select 3-7 books and rate them
        num_ratings = np.random.randint(3, 8)
        selected_books = np.random.choice(len(popular_books), size=min(num_ratings, len(popular_books)), replace=False)
        
        for idx in selected_books:
            isbn, title = popular_books[idx]
            # Generate realistic rating (skewed toward positive)
            rating = int(np.random.choice([0, 5, 6, 7, 8, 9, 10], p=[0.1, 0.1, 0.15, 0.2, 0.25, 0.15, 0.05]))
            
            r_cat = "not_rated" if rating == 0 else ("low" if rating <= 3 else ("mid" if rating <= 6 else ("high" if rating <= 8 else "very_high")))
            
            # Get sequence numbers
            with mysql_engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COALESCE(MAX(r_seq_user), 0) + 1 FROM ratings WHERE user_id = :user_id
                """), {"user_id": user_id})
                r_seq_user = result.fetchone()[0]
                
                result = conn.execute(text("""
                    SELECT COALESCE(MAX(r_seq_book), 0) + 1 FROM ratings WHERE isbn = :isbn
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
            
            print(f"  ✓ Rated '{title[:50]}...' with {rating}/10")
        
        # Update user flags
        with mysql_engine.connect() as conn:
            conn.execute(text("""
                UPDATE users SET has_ratings = TRUE WHERE user_id = :user_id
            """), {"user_id": user_id})
            conn.commit()
        
        print(f"  📊 Total ratings added: {num_ratings}\n")


def add_ratings_for_unrated_books():
    """Add ratings for books that haven't been rated yet"""
    print("=" * 80)
    print("📝 Adding Ratings for Books Without Ratings")
    print("=" * 80 + "\n")
    
    books = find_books_without_ratings(limit=5)
    
    if not books:
        print("No books without ratings found!")
        return
    
    # Get some active users
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT user_id FROM users
            WHERE has_ratings = TRUE
            LIMIT 20
        """))
        active_users = [row[0] for row in result.fetchall()]
    
    for book in books:
        isbn, title, authors, publisher = book
        print(f"Book: {title} by {authors}")
        
        # Randomly select 5-10 users to rate this book
        num_raters = np.random.randint(5, 11)
        selected_users = np.random.choice(active_users, size=min(num_raters, len(active_users)), replace=False)
        
        for user_id in selected_users:
            # Generate realistic rating
            rating = int(np.random.choice([0, 5, 6, 7, 8, 9, 10], p=[0.15, 0.15, 0.15, 0.2, 0.2, 0.10, 0.05]))
            r_cat = "not_rated" if rating == 0 else ("low" if rating <= 3 else ("mid" if rating <= 6 else ("high" if rating <= 8 else "very_high")))
            
            # Get sequence numbers
            with mysql_engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COALESCE(MAX(r_seq_user), 0) + 1 FROM ratings WHERE user_id = :user_id
                """), {"user_id": user_id})
                r_seq_user = result.fetchone()[0]
                
                result = conn.execute(text("""
                    SELECT COALESCE(MAX(r_seq_book), 0) + 1 FROM ratings WHERE isbn = :isbn
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
        
        print(f"  ✓ Added {num_raters} ratings (avg: {np.mean([r for r in [rating]]):.1f}/10)\n")


# ============================================================================
# UPDATE USER PREFERENCES
# ============================================================================

def calculate_user_preferences(user_id):
    """Calculate preferences based on user's ratings"""
    
    # Get user's highly rated books (rating >= 7)
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT r.isbn, r.rating, b.authors, b.publisher, b.publication_year
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            WHERE r.user_id = :user_id AND r.rating >= 7
        """), {"user_id": user_id})
        rated_books = result.fetchall()
    
    if not rated_books:
        return None
    
    # Calculate top genres
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rg.root_name, COUNT(*) as cnt
            FROM ratings r
            JOIN book_root_genres brg ON r.isbn = brg.isbn
            JOIN root_genres rg ON brg.root_id = rg.root_id
            WHERE r.user_id = :user_id AND r.rating >= 7
            GROUP BY rg.root_name
            ORDER BY cnt DESC
            LIMIT 3
        """), {"user_id": user_id})
        top_root_genres = [row[0] for row in result.fetchall()]
    
    # Calculate top subgenres
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT sg.subgenre_name, COUNT(*) as cnt
            FROM ratings r
            JOIN book_subgenres bsg ON r.isbn = bsg.isbn
            JOIN subgenres sg ON bsg.subgenre_id = sg.subgenre_id
            WHERE r.user_id = :user_id AND r.rating >= 7
            GROUP BY sg.subgenre_name
            ORDER BY cnt DESC
            LIMIT 5
        """), {"user_id": user_id})
        top_subgenres = [row[0] for row in result.fetchall()]
    
    # Extract top authors
    all_authors = []
    for _, _, authors, _, _ in rated_books:
        if authors:
            # Parse author list
            author_list = eval(authors) if authors.startswith('[') else [authors]
            all_authors.extend(author_list)
    
    author_counts = Counter(all_authors)
    top_authors = [author for author, _ in author_counts.most_common(5)]
    
    # Extract top publishers
    publishers = [pub for _, _, _, pub, _ in rated_books if pub]
    publisher_counts = Counter(publishers)
    top_publishers = [pub for pub, _ in publisher_counts.most_common(3)]
    
    # Calculate preferred publication years (top 3 most frequent decades)
    years = [year for _, _, _, _, year in rated_books if year]
    year_counts = Counter(years)
    top_years = [str(year) for year, _ in year_counts.most_common(3)]
    
    # Get price preferences for books they rated highly
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT r.isbn
            FROM ratings r
            WHERE r.user_id = :user_id AND r.rating >= 7
        """), {"user_id": user_id})
        highly_rated_isbns = [row[0] for row in result.fetchall()]
    
    prices = []
    for isbn in highly_rated_isbns:
        book_doc = mongo_db.books_metadata.find_one({"_id": isbn})
        if book_doc and "extra_metadata" in book_doc and "price_usd" in book_doc["extra_metadata"]:
            prices.append(book_doc["extra_metadata"]["price_usd"])
    
    if prices:
        pref_price_min = float(np.min(prices))
        pref_price_max = float(np.max(prices))
        pref_price_avg = float(np.mean(prices))
    else:
        pref_price_min = pref_price_max = pref_price_avg = None
    
    preferences = {
        "pref_root_genres": str(top_root_genres) if top_root_genres else None,
        "pref_subgenres": str(top_subgenres) if top_subgenres else None,
        "pref_authors": str(top_authors) if top_authors else None,
        "pref_publisher": str(top_publishers) if top_publishers else None,
        "pref_pub_year": str(top_years) if top_years else None,
        "pref_price_min": pref_price_min,
        "pref_price_max": pref_price_max,
        "pref_price_avg": pref_price_avg
    }
    
    return preferences


def update_user_preferences():
    """Update preferences for users who have ratings but no preferences yet"""
    print("=" * 80)
    print("🎯 Updating User Preferences Based on Ratings")
    print("=" * 80 + "\n")
    
    # Find users with ratings but no preferences
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT user_id FROM users
            WHERE has_ratings = TRUE AND has_preferences = FALSE
            LIMIT 10
        """))
        users_to_update = [row[0] for row in result.fetchall()]
    
    if not users_to_update:
        print("No users found who need preference updates!")
        return
    
    for user_id in users_to_update:
        preferences = calculate_user_preferences(user_id)
        
        if not preferences:
            print(f"⚠️  User {user_id}: Not enough high-rated books to calculate preferences")
            continue
        
        # Update MongoDB
        update_dict = {}
        for key, value in preferences.items():
            if value is not None:
                update_dict[f"preferences.{key}"] = value
        
        if update_dict:
            mongo_db.users_profiles.update_one(
                {"_id": user_id},
                {"$set": {**update_dict, "profile.has_preferences": True}}
            )
            
            # Update MySQL flag
            with mysql_engine.connect() as conn:
                conn.execute(text("""
                    UPDATE users SET has_preferences = TRUE WHERE user_id = :user_id
                """), {"user_id": user_id})
                conn.commit()
            
            print(f"✅ User {user_id}: Preferences updated")
            if preferences.get("pref_root_genres"):
                print(f"   Top genres: {preferences['pref_root_genres']}")
            if preferences.get("pref_authors"):
                print(f"   Top authors: {preferences['pref_authors'][:100]}...")
        else:
            print(f"⚠️  User {user_id}: No valid preferences could be calculated")
    
    print(f"\n✅ Updated preferences for {len(users_to_update)} users")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Run all update operations"""
    print("\n" + "=" * 80)
    print("🔄 RATINGS AND PREFERENCES UPDATE SCRIPT")
    print("=" * 80 + "\n")
    
    # 1. Add ratings for users without any
    add_ratings_for_inactive_users()
    print("\n")
    
    # 2. Add ratings for books without any
    add_ratings_for_unrated_books()
    print("\n")
    
    # 3. Update user preferences based on their new ratings
    update_user_preferences()
    
    print("\n" + "=" * 80)
    print("✅ ALL UPDATES COMPLETE")
    print("=" * 80)
    print("\nSummary:")
    print("  • Added ratings for users without ratings")
    print("  • Added ratings for previously unrated books")
    print("  • Calculated and stored user preferences")
    print("  • All metrics updated in MySQL and MongoDB")
    print("\nThese updates will improve recommendation quality!")


if __name__ == "__main__":
    try:
        main()
    finally:
        mongo_client.close()
