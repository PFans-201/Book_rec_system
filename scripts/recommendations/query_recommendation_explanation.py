"""
Recommendation Explanation Generator
Generates human-readable explanations for why a book is recommended.
Provides transparency and helps users understand recommendations.
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


def generate_explanation(user_id, isbn):
    """Generate comprehensive recommendation explanation"""
    
    explanations = []
    
    # Get book info
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT title, authors FROM books WHERE isbn = :isbn
        """), {"isbn": isbn})
        row = result.fetchone()
        
        if not row:
            return None
        
        book_title = row[0]
        book_authors = row[1]
    
    # 1. Genre-based reasons
    genre_reasons = explain_genre_match(user_id, isbn)
    explanations.extend(genre_reasons)
    
    # 2. Author-based reasons
    author_reasons = explain_author_match(user_id, book_authors)
    explanations.extend(author_reasons)
    
    # 3. Similar users reasons
    similar_user_reasons = explain_similar_users(user_id, isbn)
    explanations.extend(similar_user_reasons)
    
    # 4. Quality reasons
    quality_reasons = explain_quality(isbn)
    explanations.extend(quality_reasons)
    
    # 5. Similar books reasons
    similar_book_reasons = explain_similar_books(user_id, isbn)
    explanations.extend(similar_book_reasons)
    
    return {
        "book_title": book_title,
        "isbn": isbn,
        "explanations": explanations
    }


def explain_genre_match(user_id, isbn):
    """Explain genre-based recommendation"""
    reasons = []
    
    # Get book genres
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rg.genre_name
            FROM books_subgenres bs
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE bs.isbn = :isbn
        """), {"isbn": isbn})
        book_genres = [row[0] for row in result.fetchall()]
    
    if not book_genres:
        return reasons
    
    # Check user's favorite genres
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
        
        user_fav_genres = {row[0]: row[1] for row in result.fetchall()}
    
    # Find matches
    for genre in book_genres:
        if genre in user_fav_genres:
            count = user_fav_genres[genre]
            reasons.append({
                "type": "genre",
                "strength": "strong" if count >= 5 else "moderate",
                "text": f"This book is in the {genre} genre, which you've enjoyed in {count} other books"
            })
    
    return reasons


def explain_author_match(user_id, book_authors):
    """Explain author-based recommendation"""
    reasons = []
    
    if not book_authors:
        return reasons
    
    book_author_list = [a.strip().strip("'\"[]") for a in book_authors.split(",")]
    
    # Check if user has read these authors
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT b.authors, r.rating
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            WHERE r.user_id = :user_id AND r.rating >= 7
        """), {"user_id": user_id})
        
        user_authors = Counter()
        user_author_ratings = {}
        
        for row in result.fetchall():
            authors_str, rating = row
            if authors_str:
                authors = [a.strip().strip("'\"[]") for a in authors_str.split(",")]
                for author in authors:
                    user_authors[author] += 1
                    if author not in user_author_ratings:
                        user_author_ratings[author] = []
                    user_author_ratings[author].append(rating)
    
    # Check matches
    for author in book_author_list:
        if author in user_authors:
            count = user_authors[author]
            avg_rating = sum(user_author_ratings[author]) / len(user_author_ratings[author])
            
            reasons.append({
                "type": "author",
                "strength": "strong",
                "text": f"You've enjoyed {count} other books by {author} (average rating: {avg_rating:.1f}/10)"
            })
    
    return reasons


def explain_similar_users(user_id, isbn):
    """Explain collaborative filtering reason"""
    reasons = []
    
    # Find if similar users rated this book highly
    with mysql_engine.connect() as conn:
        # Get user's ratings
        result = conn.execute(text("""
            SELECT isbn, rating FROM ratings WHERE user_id = :user_id LIMIT 50
        """), {"user_id": user_id})
        user_ratings = {row[0]: row[1] for row in result.fetchall()}
        
        if not user_ratings:
            return reasons
        
        user_isbns = tuple(user_ratings.keys())
        
        # Find users who rated similar books similarly
        result = conn.execute(text("""
            SELECT r1.user_id, COUNT(*) as common_books
            FROM ratings r1
            WHERE r1.isbn IN :isbns AND r1.user_id != :user_id
            GROUP BY r1.user_id
            HAVING common_books >= 5
            ORDER BY common_books DESC
            LIMIT 10
        """), {"isbns": user_isbns, "user_id": user_id})
        
        similar_users = [row[0] for row in result.fetchall()]
        
        if not similar_users:
            return reasons
        
        # Check if they rated the target book
        result = conn.execute(text("""
            SELECT COUNT(*), AVG(rating)
            FROM ratings
            WHERE user_id IN :similar_users AND isbn = :isbn AND rating >= 7
        """), {"similar_users": tuple(similar_users), "isbn": isbn})
        
        row = result.fetchone()
        if row and row[0] and row[0] > 0:
            count = row[0]
            avg_rating = row[1]
            reasons.append({
                "type": "collaborative",
                "strength": "strong" if count >= 3 else "moderate",
                "text": f"{count} readers with similar taste rated this book highly (average: {avg_rating:.1f}/10)"
            })
    
    return reasons


def explain_quality(isbn):
    """Explain quality-based recommendation"""
    reasons = []
    
    # Get book quality metrics from MongoDB
    book_meta = mongo_db.books_metadata.find_one({"_id": isbn})
    
    if book_meta and "rating_metrics" in book_meta:
        rm = book_meta["rating_metrics"]
        r_avg = rm.get("r_avg", 0)
        r_count = rm.get("r_count", 0)
        rating_score = rm.get("rating_score", 0)
        
        if rating_score >= 7:
            reasons.append({
                "type": "quality",
                "strength": "strong" if rating_score >= 8 else "moderate",
                "text": f"Highly rated book ({r_avg:.1f}/10 from {r_count} readers, quality score: {rating_score:.1f})"
            })
        elif r_avg >= 7:
            reasons.append({
                "type": "quality",
                "strength": "moderate",
                "text": f"Well-rated book ({r_avg:.1f}/10 from {r_count} readers)"
            })
    
    return reasons


def explain_similar_books(user_id, isbn):
    """Explain based on similar books user has read"""
    reasons = []
    
    # Get book genres
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rg.genre_name
            FROM books_subgenres bs
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE bs.isbn = :isbn
        """), {"isbn": isbn})
        target_genres = [row[0] for row in result.fetchall()]
        
        if not target_genres:
            return reasons
        
        # Find similar books user has rated highly
        result = conn.execute(text("""
            SELECT b.title, r.rating
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            JOIN books_subgenres bs ON b.isbn = bs.isbn
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE r.user_id = :user_id AND r.rating >= 8
              AND rg.genre_name IN :genres
              AND b.isbn != :isbn
            LIMIT 3
        """), {"user_id": user_id, "genres": tuple(target_genres), "isbn": isbn})
        
        similar_books = [(row[0], row[1]) for row in result.fetchall()]
        
        if similar_books:
            book_titles = ", ".join([f'"{title}"' for title, _ in similar_books[:2]])
            reasons.append({
                "type": "similarity",
                "strength": "moderate",
                "text": f"Similar to books you loved like {book_titles}"
            })
    
    return reasons


def format_explanation(result):
    """Format explanation in human-readable way"""
    if not result:
        return None
    
    # Group by strength
    strong_reasons = [e for e in result["explanations"] if e["strength"] == "strong"]
    moderate_reasons = [e for e in result["explanations"] if e["strength"] == "moderate"]
    
    return {
        "book_title": result["book_title"],
        "isbn": result["isbn"],
        "primary_reasons": strong_reasons,
        "secondary_reasons": moderate_reasons,
        "summary": generate_summary(result["book_title"], strong_reasons, moderate_reasons)
    }


def generate_summary(book_title, strong_reasons, moderate_reasons):
    """Generate a one-paragraph summary"""
    if not strong_reasons and not moderate_reasons:
        return f'We recommend "{book_title}" based on general popularity.'
    
    summary_parts = [f'We recommend "{book_title}" because:']
    
    if strong_reasons:
        reason_texts = [r["text"].lower() for r in strong_reasons[:2]]
        summary_parts.append(" " + ", and ".join(reason_texts))
    
    if moderate_reasons and len(strong_reasons) < 2:
        reason_texts = [r["text"].lower() for r in moderate_reasons[:1]]
        if strong_reasons:
            summary_parts.append("; additionally, " + reason_texts[0])
        else:
            summary_parts.append(" " + reason_texts[0])
    
    return "".join(summary_parts) + "."


def display_explanation(explanation):
    """Display recommendation explanation"""
    print("\n" + "=" * 80)
    print("💬 RECOMMENDATION EXPLANATION")
    print("=" * 80)
    
    print(f"\nBook: {explanation['book_title']}")
    print(f"ISBN: {explanation['isbn']}")
    
    print("\n" + "=" * 80)
    print("WHY WE RECOMMEND THIS BOOK")
    print("=" * 80)
    
    print(f"\n{explanation['summary']}")
    
    if explanation["primary_reasons"]:
        print("\n🌟 Primary Reasons:")
        for i, reason in enumerate(explanation["primary_reasons"], 1):
            print(f"  {i}. {reason['text']}")
    
    if explanation["secondary_reasons"]:
        print("\n✨ Additional Reasons:")
        for i, reason in enumerate(explanation["secondary_reasons"], 1):
            print(f"  {i}. {reason['text']}")


def main():
    parser = argparse.ArgumentParser(description="Explain book recommendation")
    parser.add_argument("--user_id", type=int, required=True, help="User ID")
    parser.add_argument("--isbn", type=str, required=True, help="Book ISBN")
    
    args = parser.parse_args()
    
    try:
        print(f"\n🔍 Generating explanation for User {args.user_id} and ISBN {args.isbn}...")
        
        result = generate_explanation(args.user_id, args.isbn)
        
        if not result:
            print(f"\n⚠️  Book with ISBN {args.isbn} not found")
            return
        
        explanation = format_explanation(result)
        display_explanation(explanation)
    
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
