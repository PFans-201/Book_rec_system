"""
User-Book Compatibility Score Calculator
Calculates how well a book matches a user's profile and preferences.
Provides detailed compatibility metrics and explanations.
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


def get_user_profile(user_id):
    """Get comprehensive user profile"""
    # MongoDB preferences
    user_profile = mongo_db.users_profiles.find_one({"_id": user_id})
    preferences = user_profile.get("preferences", {}) if user_profile else {}
    
    # MySQL profile data
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT reader_level, critic_profile, mean_rating, median_rating, std_rating
            FROM users WHERE user_id = :user_id
        """), {"user_id": user_id})
        row = result.fetchone()
        
        profile = {}
        if row:
            profile = {
                "reader_level": row[0],
                "critic_profile": row[1],
                "mean_rating": float(row[2]) if row[2] else None,
                "median_rating": float(row[3]) if row[3] else None,
                "std_rating": float(row[4]) if row[4] else None
            }
    
    return {**profile, "preferences": preferences}


def get_user_favorite_genres(user_id, limit=5):
    """Get user's favorite genres"""
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
            LIMIT :limit
        """), {"user_id": user_id, "limit": limit})
        
        return [row[0] for row in result.fetchall()]


def get_book_info(isbn):
    """Get comprehensive book information"""
    # MySQL data
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT title, authors, publisher, publication_year
            FROM books WHERE isbn = :isbn
        """), {"isbn": isbn})
        row = result.fetchone()
        
        if not row:
            return None
        
        book_info = {
            "isbn": isbn,
            "title": row[0],
            "authors": row[1],
            "publisher": row[2],
            "publication_year": row[3]
        }
        
        # Get genres
        result = conn.execute(text("""
            SELECT rg.genre_name
            FROM books_subgenres bs
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE bs.isbn = :isbn
        """), {"isbn": isbn})
        book_info["genres"] = [row[0] for row in result.fetchall()]
    
    # MongoDB metadata
    book_meta = mongo_db.books_metadata.find_one({"_id": isbn})
    if book_meta:
        book_info["metadata"] = book_meta
    
    return book_info


def calculate_genre_compatibility(user_genres, book_genres):
    """Calculate genre match score"""
    if not user_genres or not book_genres:
        return 0, []
    
    matches = set(user_genres).intersection(set(book_genres))
    if not matches:
        return 0, []
    
    score = len(matches) * 20
    reasons = [f"Matches {len(matches)} of your favorite genres: {', '.join(matches)}"]
    
    return score, reasons


def calculate_author_compatibility(user_id, book_authors):
    """Calculate author familiarity score"""
    # Get user's highly rated books' authors
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT b.authors
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            WHERE r.user_id = :user_id AND r.rating >= 7
        """), {"user_id": user_id})
        
        user_author_counts = Counter()
        for row in result.fetchall():
            authors_str = row[0]
            if authors_str:
                authors = [a.strip().strip("'\"[]") for a in authors_str.split(",")]
                user_author_counts.update(authors)
    
    # Check if book authors are familiar
    if not book_authors:
        return 0, []
    
    book_author_list = [a.strip().strip("'\"[]") for a in book_authors.split(",")]
    
    score = 0
    reasons = []
    for author in book_author_list:
        if author in user_author_counts:
            count = user_author_counts[author]
            author_score = min(count * 5, 25)  # Cap at 25
            score += author_score
            reasons.append(f"Familiar author: {author} (you've read {count} of their books)")
    
    return score, reasons


def calculate_price_compatibility(user_prefs, book_price):
    """Calculate price fit score"""
    if not user_prefs or "avg_price" not in user_prefs or not book_price:
        return 0, []
    
    user_avg_price = user_prefs["avg_price"]
    price_diff = abs(book_price - user_avg_price)
    
    if price_diff <= 5:
        return 15, [f"Price (${book_price:.2f}) matches your average (${user_avg_price:.2f})"]
    elif price_diff <= 10:
        return 8, [f"Price (${book_price:.2f}) close to your average (${user_avg_price:.2f})"]
    else:
        return 0, [f"Price (${book_price:.2f}) differs from your average (${user_avg_price:.2f})"]


def calculate_quality_compatibility(user_profile, book_metadata):
    """Calculate quality alignment score"""
    if not book_metadata or "rating_metrics" not in book_metadata:
        return 0, []
    
    rm = book_metadata["rating_metrics"]
    book_avg = rm.get("r_avg", 0)
    
    # Check critic profile alignment
    critic_profile = user_profile.get("critic_profile")
    reader_level = user_profile.get("reader_level")
    
    score = 0
    reasons = []
    
    # Harsh critics prefer higher quality
    if critic_profile == "harsh_critic" and book_avg >= 8:
        score += 20
        reasons.append(f"High quality book ({book_avg}/10) suits your harsh critic profile")
    elif critic_profile == "generous_reader" and book_avg >= 6:
        score += 15
        reasons.append(f"Good book ({book_avg}/10) suits your generous reading style")
    elif critic_profile == "average_rater":
        if 6 <= book_avg <= 8:
            score += 15
            reasons.append(f"Average quality book ({book_avg}/10) suits your rating style")
    
    # Reader level alignment
    r_category = rm.get("r_category", "")
    if reader_level == "voracious_reader" and r_category in ["popular", "highly_rated"]:
        score += 10
        reasons.append("Popular book suits voracious reader profile")
    
    return score, reasons


def calculate_popularity_compatibility(user_profile, book_metadata):
    """Calculate popularity alignment score"""
    if not book_metadata or "popularity_metrics" not in book_metadata:
        return 0, []
    
    pm = book_metadata["popularity_metrics"]
    popularity_score = pm.get("popularity_score", 0)
    
    reader_level = user_profile.get("reader_level", "")
    
    score = 0
    reasons = []
    
    if reader_level in ["voracious_reader", "active_reader"] and popularity_score > 5:
        score += 10
        reasons.append("Popular book suits your active reading profile")
    elif reader_level in ["occasional_reader", "new_reader"] and popularity_score > 7:
        score += 15
        reasons.append("Well-known book good for your reading level")
    
    return score, reasons


def calculate_compatibility(user_id, isbn):
    """Calculate comprehensive compatibility score"""
    
    # Get user profile
    user_profile = get_user_profile(user_id)
    user_genres = get_user_favorite_genres(user_id)
    
    # Get book info
    book_info = get_book_info(isbn)
    if not book_info:
        return None
    
    # Calculate component scores
    components = {}
    
    # Genre compatibility
    genre_score, genre_reasons = calculate_genre_compatibility(user_genres, book_info.get("genres", []))
    components["genre"] = {"score": genre_score, "reasons": genre_reasons}
    
    # Author compatibility
    author_score, author_reasons = calculate_author_compatibility(user_id, book_info.get("authors", ""))
    components["author"] = {"score": author_score, "reasons": author_reasons}
    
    # Price compatibility
    book_price = book_info.get("metadata", {}).get("price") if "metadata" in book_info else None
    price_score, price_reasons = calculate_price_compatibility(user_profile.get("preferences"), book_price)
    components["price"] = {"score": price_score, "reasons": price_reasons}
    
    # Quality compatibility
    quality_score, quality_reasons = calculate_quality_compatibility(
        user_profile, 
        book_info.get("metadata")
    )
    components["quality"] = {"score": quality_score, "reasons": quality_reasons}
    
    # Popularity compatibility
    pop_score, pop_reasons = calculate_popularity_compatibility(
        user_profile,
        book_info.get("metadata")
    )
    components["popularity"] = {"score": pop_score, "reasons": pop_reasons}
    
    # Total score
    total_score = sum(comp["score"] for comp in components.values())
    
    return {
        "book": book_info,
        "user_profile": user_profile,
        "total_score": total_score,
        "components": components,
        "compatibility_level": get_compatibility_level(total_score)
    }


def get_compatibility_level(score):
    """Get compatibility level label"""
    if score >= 80:
        return "Excellent Match"
    elif score >= 60:
        return "Great Match"
    elif score >= 40:
        return "Good Match"
    elif score >= 20:
        return "Fair Match"
    else:
        return "Poor Match"


def display_compatibility(result):
    """Display compatibility analysis"""
    print("\n" + "=" * 80)
    print("🎯 USER-BOOK COMPATIBILITY ANALYSIS")
    print("=" * 80)
    
    book = result["book"]
    print(f"\nBook: {book['title']}")
    print(f"ISBN: {book['isbn']}")
    print(f"Authors: {book['authors']}")
    print(f"Genres: {', '.join(book.get('genres', []))}")
    
    print("\n" + "=" * 80)
    print(f"COMPATIBILITY SCORE: {result['total_score']:.0f}/100")
    print(f"Level: {result['compatibility_level']}")
    print("=" * 80)
    
    print("\nScore Breakdown:")
    for component, data in result["components"].items():
        print(f"\n{component.title()}: {data['score']:.0f} points")
        for reason in data["reasons"]:
            print(f"  • {reason}")
        if not data["reasons"]:
            print("  • No match")
    
    if "metadata" in book and "rating_metrics" in book["metadata"]:
        rm = book["metadata"]["rating_metrics"]
        print(f"\nBook Statistics:")
        print(f"  • Average Rating: {rm.get('r_avg', 'N/A')}/10")
        print(f"  • Total Ratings: {rm.get('r_count', 0)}")
        print(f"  • Quality Score: {rm.get('rating_score', 'N/A')}")


def main():
    parser = argparse.ArgumentParser(description="Calculate user-book compatibility")
    parser.add_argument("--user_id", type=int, required=True, help="User ID")
    parser.add_argument("--isbn", type=str, required=True, help="Book ISBN")
    
    args = parser.parse_args()
    
    try:
        print(f"\n🔍 Calculating compatibility for User {args.user_id} and ISBN {args.isbn}...")
        
        result = calculate_compatibility(args.user_id, args.isbn)
        
        if not result:
            print(f"\n⚠️  Book with ISBN {args.isbn} not found")
            return
        
        display_compatibility(result)
    
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
