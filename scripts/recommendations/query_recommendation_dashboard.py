"""
Recommendation Dashboard Generator
Generates comprehensive recommendation report combining multiple strategies.
Provides a holistic view of personalized recommendations.
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


def get_user_summary(user_id):
    """Get user profile summary"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT reader_level, critic_profile, age_group, gender,
                   mean_rating, has_preferences
            FROM users WHERE user_id = :user_id
        """), {"user_id": user_id})
        row = result.fetchone()
        
        if not row:
            return None
        
        # Get rating count
        result = conn.execute(text("""
            SELECT COUNT(*) FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        rating_count = result.fetchone()[0] or 0
        
        return {
            "reader_level": row[0],
            "critic_profile": row[1],
            "age_group": row[2],
            "gender": row[3],
            "mean_rating": float(row[4]) if row[4] else None,
            "has_preferences": bool(row[5]),
            "rating_count": rating_count
        }


def get_content_based_picks(user_id, limit=5):
    """Get content-based recommendations"""
    # Get favorite genres
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
            LIMIT 3
        """), {"user_id": user_id})
        
        fav_genres = [row[0] for row in result.fetchall()]
        
        if not fav_genres:
            return []
        
        # Get rated books
        result = conn.execute(text("""
            SELECT isbn FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        rated_isbns = {row[0] for row in result.fetchall()}
        
        # Find books in favorite genres
        result = conn.execute(text("""
            SELECT DISTINCT b.isbn, b.title, b.authors
            FROM books b
            JOIN books_subgenres bs ON b.isbn = bs.isbn
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE rg.genre_name IN :genres
            LIMIT 50
        """), {"genres": tuple(fav_genres)})
        
        candidates = [{"isbn": row[0], "title": row[1], "authors": row[2]} 
                     for row in result.fetchall() if row[0] not in rated_isbns]
        
        # Score by MongoDB quality
        scored = []
        for book in candidates:
            book_meta = mongo_db.books_metadata.find_one({"_id": book["isbn"]})
            if book_meta and "rating_metrics" in book_meta:
                score = book_meta["rating_metrics"].get("rating_score", 0)
                if score >= 5:
                    scored.append({**book, "score": score, "type": "content"})
        
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]


def get_trending_picks(user_id, limit=5):
    """Get trending books"""
    # Get max sequence
    with mysql_engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(r_seq_book) FROM ratings"))
        max_seq = result.fetchone()[0]
        
        if not max_seq:
            return []
        
        recent_threshold = max_seq * 0.9  # Last 10%
        
        # Get rated books
        result = conn.execute(text("""
            SELECT isbn FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        rated_isbns = {row[0] for row in result.fetchall()}
        
        # Find trending books
        result = conn.execute(text("""
            SELECT isbn, COUNT(*) as recent_count, AVG(rating) as recent_avg
            FROM ratings
            WHERE r_seq_book >= :threshold
            GROUP BY isbn
            HAVING recent_count >= 5
            ORDER BY recent_count DESC
            LIMIT 20
        """), {"threshold": recent_threshold})
        
        trending = []
        for row in result.fetchall():
            isbn, count, avg_rating = row
            if isbn not in rated_isbns:
                # Get title
                book_result = conn.execute(text("""
                    SELECT title, authors FROM books WHERE isbn = :isbn
                """), {"isbn": isbn})
                book_row = book_result.fetchone()
                
                if book_row:
                    trending.append({
                        "isbn": isbn,
                        "title": book_row[0],
                        "authors": book_row[1],
                        "score": count * avg_rating,
                        "type": "trending"
                    })
        
        trending.sort(key=lambda x: x["score"], reverse=True)
        return trending[:limit]


def get_hidden_gems(user_id, limit=5):
    """Get high-quality but less popular books"""
    # Get favorite genres
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rg.genre_name
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            JOIN books_subgenres bs ON b.isbn = bs.isbn
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE r.user_id = :user_id AND r.rating >= 7
            GROUP BY rg.genre_name
            ORDER BY COUNT(*) DESC
            LIMIT 3
        """), {"user_id": user_id})
        
        fav_genres = [row[0] for row in result.fetchall()]
        
        if not fav_genres:
            return []
        
        # Get rated books
        result = conn.execute(text("""
            SELECT isbn FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        rated_isbns = {row[0] for row in result.fetchall()}
        
        # Find books in favorite genres
        result = conn.execute(text("""
            SELECT DISTINCT b.isbn, b.title, b.authors
            FROM books b
            JOIN books_subgenres bs ON b.isbn = bs.isbn
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE rg.genre_name IN :genres
            LIMIT 100
        """), {"genres": tuple(fav_genres)})
        
        candidates = [{"isbn": row[0], "title": row[1], "authors": row[2]}
                     for row in result.fetchall() if row[0] not in rated_isbns]
    
    # Find gems: high quality, low popularity
    gems = []
    for book in candidates:
        book_meta = mongo_db.books_metadata.find_one({"_id": book["isbn"]})
        if book_meta and "rating_metrics" in book_meta:
            rm = book_meta["rating_metrics"]
            r_avg = rm.get("r_avg", 0)
            r_count = rm.get("r_count", 0)
            
            # Hidden gem criteria: high quality (>=7.5), low count (<100)
            if r_avg >= 7.5 and 10 <= r_count < 100:
                gems.append({
                    **book,
                    "score": r_avg,
                    "rating_count": r_count,
                    "type": "hidden_gem"
                })
    
    gems.sort(key=lambda x: x["score"], reverse=True)
    return gems[:limit]


def get_new_releases(user_id, limit=5):
    """Get recent books in favorite genres"""
    with mysql_engine.connect() as conn:
        # Get favorite genres
        result = conn.execute(text("""
            SELECT rg.genre_name
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            JOIN books_subgenres bs ON b.isbn = bs.isbn
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE r.user_id = :user_id AND r.rating >= 7
            GROUP BY rg.genre_name
            ORDER BY COUNT(*) DESC
            LIMIT 3
        """), {"user_id": user_id})
        
        fav_genres = [row[0] for row in result.fetchall()]
        
        if not fav_genres:
            return []
        
        # Get rated books
        result = conn.execute(text("""
            SELECT isbn FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        rated_isbns = {row[0] for row in result.fetchall()}
        
        # Find recent books (last 5 years from max year)
        result = conn.execute(text("""
            SELECT MAX(publication_year) FROM books
            WHERE publication_year IS NOT NULL AND publication_year != ''
        """))
        max_year_row = result.fetchone()
        max_year = int(max_year_row[0]) if max_year_row and max_year_row[0] else 2023
        
        recent_threshold = max_year - 5
        
        result = conn.execute(text("""
            SELECT DISTINCT b.isbn, b.title, b.authors, b.publication_year
            FROM books b
            JOIN books_subgenres bs ON b.isbn = bs.isbn
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE rg.genre_name IN :genres
              AND CAST(b.publication_year AS SIGNED) >= :threshold
            LIMIT 50
        """), {"genres": tuple(fav_genres), "threshold": recent_threshold})
        
        new_books = []
        for row in result.fetchall():
            isbn, title, authors, year = row
            if isbn not in rated_isbns:
                # Get rating from MongoDB
                book_meta = mongo_db.books_metadata.find_one({"_id": isbn})
                score = 0
                if book_meta and "rating_metrics" in book_meta:
                    score = book_meta["rating_metrics"].get("rating_score", 0)
                
                if score >= 5:
                    new_books.append({
                        "isbn": isbn,
                        "title": title,
                        "authors": authors,
                        "year": year,
                        "score": score,
                        "type": "new_release"
                    })
        
        new_books.sort(key=lambda x: (x["year"], x["score"]), reverse=True)
        return new_books[:limit]


def display_dashboard(user_id, summary, content_picks, trending, gems, new_releases):
    """Display recommendation dashboard"""
    print("\n" + "=" * 80)
    print("🎯 PERSONALIZED RECOMMENDATION DASHBOARD")
    print("=" * 80)
    
    print(f"\nUser ID: {user_id}")
    if summary:
        print(f"Reader Level: {summary['reader_level']}")
        print(f"Critic Profile: {summary['critic_profile']}")
        print(f"Books Rated: {summary['rating_count']}")
        if summary['mean_rating']:
            print(f"Average Rating: {summary['mean_rating']:.2f}/10")
    
    # Content-Based Picks
    if content_picks:
        print("\n" + "=" * 80)
        print("📚 PERFECT FOR YOUR TASTE (Content-Based)")
        print("=" * 80)
        for i, book in enumerate(content_picks, 1):
            print(f"\n{i}. {book['title']}")
            print(f"   Authors: {book['authors']}")
            print(f"   Quality Score: {book['score']:.1f}")
    
    # Trending
    if trending:
        print("\n" + "=" * 80)
        print("🔥 TRENDING NOW")
        print("=" * 80)
        for i, book in enumerate(trending, 1):
            print(f"\n{i}. {book['title']}")
            print(f"   Authors: {book['authors']}")
            print(f"   Trending Score: {book['score']:.1f}")
    
    # Hidden Gems
    if gems:
        print("\n" + "=" * 80)
        print("💎 HIDDEN GEMS (High Quality, Under the Radar)")
        print("=" * 80)
        for i, book in enumerate(gems, 1):
            print(f"\n{i}. {book['title']}")
            print(f"   Authors: {book['authors']}")
            print(f"   Rating: {book['score']:.1f}/10 ({book['rating_count']} ratings)")
    
    # New Releases
    if new_releases:
        print("\n" + "=" * 80)
        print("✨ NEW RELEASES IN YOUR FAVORITE GENRES")
        print("=" * 80)
        for i, book in enumerate(new_releases, 1):
            print(f"\n{i}. {book['title']}")
            print(f"   Authors: {book['authors']}")
            print(f"   Year: {book['year']}")
            print(f"   Quality Score: {book['score']:.1f}")


def main():
    parser = argparse.ArgumentParser(description="Generate recommendation dashboard")
    parser.add_argument("--user_id", type=int, required=True, help="User ID")
    parser.add_argument("--per_category", type=int, default=5, help="Recommendations per category")
    
    args = parser.parse_args()
    
    try:
        print(f"\n🔍 Generating dashboard for User {args.user_id}...")
        
        # Get user summary
        summary = get_user_summary(args.user_id)
        
        if not summary:
            print(f"\n⚠️  User {args.user_id} not found")
            return
        
        # Get recommendations from different strategies
        content_picks = get_content_based_picks(args.user_id, args.per_category)
        trending = get_trending_picks(args.user_id, args.per_category)
        gems = get_hidden_gems(args.user_id, args.per_category)
        new_releases = get_new_releases(args.user_id, args.per_category)
        
        # Display dashboard
        display_dashboard(args.user_id, summary, content_picks, trending, gems, new_releases)
    
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
