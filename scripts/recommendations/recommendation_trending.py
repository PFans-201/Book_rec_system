"""
Trending Books Recommendation System
Identifies and recommends books that are gaining momentum recently.
Uses recent ratings velocity, recency-weighted scores, and upward trends.
"""

from pathlib import Path
import sys
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import argparse
from datetime import datetime, timedelta

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


def get_trending_books_by_velocity(min_recent_ratings=10, recent_window_pct=10, limit=50):
    """
    Find books with high recent rating velocity.
    Uses r_seq_book to identify recent ratings (higher seq = more recent).
    """
    
    # Get max r_seq_book to define "recent"
    with mysql_engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(r_seq_book) FROM ratings"))
        max_seq = result.fetchone()[0]
    
    if not max_seq:
        return []
    
    # Define recent as top N% of sequence numbers
    recent_threshold = max_seq * (1 - recent_window_pct / 100)
    
    # Find books with high velocity (many recent ratings with high quality)
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                isbn,
                COUNT(*) as recent_count,
                AVG(rating) as recent_avg_rating,
                MAX(r_seq_book) as latest_seq
            FROM ratings
            WHERE r_seq_book >= :threshold
            GROUP BY isbn
            HAVING recent_count >= :min_count
            ORDER BY recent_count DESC, recent_avg_rating DESC
            LIMIT :limit
        """), {
            "threshold": recent_threshold,
            "min_count": min_recent_ratings,
            "limit": limit
        })
        
        trending = []
        for row in result.fetchall():
            isbn, recent_count, recent_avg, latest_seq = row
            trending.append({
                "isbn": isbn,
                "recent_count": recent_count,
                "recent_avg_rating": recent_avg,
                "latest_seq": latest_seq,
                "velocity_score": recent_count * (recent_avg / 10)
            })
    
    return trending


def calculate_momentum_score(isbn):
    """
    Calculate momentum by comparing recent vs. older ratings.
    Positive momentum = recent ratings better than historical average.
    """
    with mysql_engine.connect() as conn:
        # Get total rating count to split recent/old
        result = conn.execute(text("""
            SELECT COUNT(*) FROM ratings WHERE isbn = :isbn
        """), {"isbn": isbn})
        total_count = result.fetchone()[0]
        
        if total_count < 20:  # Need enough history
            return 0
        
        # Get recent ratings (top 30%)
        recent_threshold = int(total_count * 0.7)
        
        # Recent ratings
        result = conn.execute(text("""
            SELECT AVG(rating) 
            FROM (
                SELECT rating 
                FROM ratings 
                WHERE isbn = :isbn 
                ORDER BY r_seq_book DESC 
                LIMIT :recent_limit
            ) recent
        """), {"isbn": isbn, "recent_limit": total_count - recent_threshold})
        recent_avg = result.fetchone()[0]
        
        # Older ratings
        result = conn.execute(text("""
            SELECT AVG(rating) 
            FROM (
                SELECT rating 
                FROM ratings 
                WHERE isbn = :isbn 
                ORDER BY r_seq_book ASC 
                LIMIT :old_limit
            ) old
        """), {"isbn": isbn, "old_limit": recent_threshold})
        old_avg = result.fetchone()[0]
        
        if recent_avg and old_avg:
            momentum = recent_avg - old_avg
            return momentum
    
    return 0


def get_user_preferred_genres(user_id):
    """Get user's favorite genres to filter trending books"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rg.genre_name, COUNT(*) as count
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            JOIN books_subgenres bs ON b.isbn = bs.isbn
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE r.user_id = :user_id AND r.rating >= 7
            GROUP BY rg.genre_name
            ORDER BY count DESC
            LIMIT 5
        """), {"user_id": user_id})
        return [row[0] for row in result.fetchall()]


def filter_by_user_preferences(trending_books, user_id, genre_filter=True):
    """Filter trending books by user's genre preferences"""
    if not genre_filter or not user_id:
        return trending_books
    
    user_genres = get_user_preferred_genres(user_id)
    if not user_genres:
        return trending_books
    
    filtered = []
    for book in trending_books:
        book_meta = mongo_db.books_metadata.find_one({"_id": book["isbn"]})
        
        if book_meta and "genres" in book_meta:
            book_genres = book_meta["genres"]
            if any(genre in book_genres for genre in user_genres):
                book["genre_match"] = True
                filtered.append(book)
    
    # If filtering removes everything, return unfiltered
    return filtered if filtered else trending_books


def enrich_trending_books(trending_books, calculate_momentum=True):
    """Add book details and momentum scores"""
    enriched = []
    
    for book in trending_books:
        isbn = book["isbn"]
        
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
        
        # Calculate momentum if requested
        momentum = 0
        if calculate_momentum:
            momentum = calculate_momentum_score(isbn)
        
        enriched.append({
            **book,
            "title": title,
            "authors": authors,
            "publisher": publisher,
            "publication_year": pub_year,
            "momentum": momentum,
            "metadata": book_meta
        })
    
    return enriched


def display_trending(trending_books, user_id=None):
    """Display trending recommendations"""
    print("\n" + "=" * 80)
    print("🔥 TRENDING BOOKS")
    print("=" * 80)
    
    if user_id:
        print(f"\nFiltered for User {user_id}'s preferences")
    
    print("\n" + "=" * 80)
    print("📚 HOT RIGHT NOW")
    print("=" * 80)
    
    for i, book in enumerate(trending_books, 1):
        print(f"\n{i}. {book['title']}")
        print(f"   ISBN: {book['isbn']}")
        print(f"   Authors: {book['authors']}")
        print(f"   📈 Velocity Score: {book['velocity_score']:.2f}")
        print(f"   🔥 Recent Activity: {book['recent_count']} ratings (avg: {book['recent_avg_rating']:.1f}/10)")
        
        if book.get('momentum'):
            momentum_emoji = "⬆️" if book['momentum'] > 0 else "⬇️"
            print(f"   {momentum_emoji} Momentum: {book['momentum']:+.2f} (recent vs. historical)")
        
        if book.get('genre_match'):
            print("   ✨ Matches your favorite genres")
        
        # Show global metrics
        if book.get('metadata') and 'rating_metrics' in book['metadata']:
            rm = book['metadata']['rating_metrics']
            print(f"   Overall: {rm.get('r_avg', 'N/A')}/10 ({rm.get('r_count', 0)} total ratings)")


def main():
    parser = argparse.ArgumentParser(description="Trending books recommendations")
    parser.add_argument("--user_id", type=int, help="Optional: Filter by user preferences")
    parser.add_argument("--limit", type=int, default=20, help="Number of trending books")
    parser.add_argument("--recent_window", type=int, default=10, 
                       help="Recent window percentage (default: 10%)")
    parser.add_argument("--min_ratings", type=int, default=10,
                       help="Minimum recent ratings required")
    parser.add_argument("--no_momentum", action="store_true",
                       help="Skip momentum calculation for speed")
    parser.add_argument("--no_filter", action="store_true",
                       help="Don't filter by user preferences")
    
    args = parser.parse_args()
    
    try:
        print(f"\n🔍 Finding trending books...")
        
        trending = get_trending_books_by_velocity(
            min_recent_ratings=args.min_ratings,
            recent_window_pct=args.recent_window,
            limit=args.limit * 2  # Get extra for filtering
        )
        
        if not trending:
            print("\n⚠️  No trending books found")
            return
        
        # Filter by user preferences if specified
        if args.user_id and not args.no_filter:
            trending = filter_by_user_preferences(trending, args.user_id)
        
        # Limit after filtering
        trending = trending[:args.limit]
        
        # Enrich with details and momentum
        enriched = enrich_trending_books(trending, calculate_momentum=not args.no_momentum)
        
        # Sort by velocity score
        enriched.sort(key=lambda x: x["velocity_score"], reverse=True)
        
        display_trending(enriched, args.user_id)
    
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
