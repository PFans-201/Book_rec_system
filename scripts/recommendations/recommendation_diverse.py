"""
Diversity-Aware Recommendation System
Provides diverse recommendations across multiple genres and authors.
Balances personalization with exploration and variety.
"""

from pathlib import Path
import sys
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import argparse
from collections import defaultdict, Counter

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


def get_user_genre_distribution(user_id):
    """Get distribution of genres in user's reading history"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rg.genre_name, COUNT(*) as count
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            JOIN books_subgenres bs ON b.isbn = bs.isbn
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE r.user_id = :user_id
            GROUP BY rg.genre_name
            ORDER BY count DESC
        """), {"user_id": user_id})
        
        genres = {}
        for row in result.fetchall():
            genres[row[0]] = row[1]
        
        return genres


def get_user_author_distribution(user_id):
    """Get distribution of authors in user's reading history"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT b.authors
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            WHERE r.user_id = :user_id
        """), {"user_id": user_id})
        
        all_authors = []
        for row in result.fetchall():
            authors_str = row[0]
            if authors_str:
                # Parse author list
                authors = [a.strip().strip("'\"[]") for a in authors_str.split(",")]
                all_authors.extend(authors)
        
        return Counter(all_authors)


def identify_underexplored_genres(user_genres, top_n=5):
    """Identify genres user hasn't explored much"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT genre_name FROM root_genres
        """))
        all_genres = [row[0] for row in result.fetchall()]
    
    # Find genres with 0 or low count
    underexplored = []
    for genre in all_genres:
        count = user_genres.get(genre, 0)
        if count < 3:  # Less than 3 books in this genre
            underexplored.append(genre)
    
    return underexplored[:top_n]


def get_diverse_recommendations(user_id, diversity_level=0.5, limit=20):
    """
    Get diverse recommendations
    diversity_level: 0 = only familiar, 1 = only exploratory, 0.5 = balanced
    """
    
    # Get user's current distribution
    user_genres = get_user_genre_distribution(user_id)
    user_authors = get_user_author_distribution(user_id)
    
    # Get user's rated books
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT isbn FROM ratings WHERE user_id = :user_id
        """), {"user_id": user_id})
        rated_isbns = {row[0] for row in result.fetchall()}
    
    recommendations = []
    
    # Familiar recommendations (from favorite genres/authors)
    familiar_count = int(limit * (1 - diversity_level))
    if familiar_count > 0 and user_genres:
        top_genres = sorted(user_genres.items(), key=lambda x: x[1], reverse=True)[:3]
        genre_names = [g[0] for g in top_genres]
        
        with mysql_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT DISTINCT b.isbn
                FROM books b
                JOIN books_subgenres bs ON b.isbn = bs.isbn
                JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
                JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
                WHERE rg.genre_name IN :genres
                LIMIT :limit
            """), {"genres": tuple(genre_names), "limit": familiar_count * 3})
            
            familiar_candidates = [row[0] for row in result.fetchall() if row[0] not in rated_isbns]
        
        # Score familiar books
        for isbn in familiar_candidates[:familiar_count]:
            book_meta = mongo_db.books_metadata.find_one({"_id": isbn})
            if book_meta and "rating_metrics" in book_meta:
                rm = book_meta["rating_metrics"]
                recommendations.append({
                    "isbn": isbn,
                    "type": "familiar",
                    "score": rm.get("rating_score", 0),
                    "metadata": book_meta
                })
    
    # Exploratory recommendations (from underexplored genres)
    exploratory_count = limit - len(recommendations)
    if exploratory_count > 0:
        underexplored = identify_underexplored_genres(user_genres)
        
        if underexplored:
            with mysql_engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT DISTINCT b.isbn
                    FROM books b
                    JOIN books_subgenres bs ON b.isbn = bs.isbn
                    JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
                    JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
                    WHERE rg.genre_name IN :genres
                    LIMIT :limit
                """), {"genres": tuple(underexplored), "limit": exploratory_count * 3})
                
                exploratory_candidates = [row[0] for row in result.fetchall() if row[0] not in rated_isbns]
            
            # Score exploratory books (prefer high quality)
            for isbn in exploratory_candidates[:exploratory_count]:
                book_meta = mongo_db.books_metadata.find_one({"_id": isbn})
                if book_meta and "rating_metrics" in book_meta:
                    rm = book_meta["rating_metrics"]
                    if rm.get("rating_score", 0) >= 5:  # Only good quality exploratory
                        recommendations.append({
                            "isbn": isbn,
                            "type": "exploratory",
                            "score": rm.get("rating_score", 0),
                            "metadata": book_meta
                        })
    
    # Sort by score
    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations[:limit]


def ensure_author_diversity(recommendations, max_per_author=2):
    """Limit books per author to ensure diversity"""
    author_counts = defaultdict(int)
    diverse_recs = []
    
    for rec in recommendations:
        book_meta = rec.get("metadata", {})
        authors = book_meta.get("authors", "")
        
        # Count primary author (first in list)
        primary_author = authors.split(",")[0].strip() if authors else "Unknown"
        
        if author_counts[primary_author] < max_per_author:
            diverse_recs.append(rec)
            author_counts[primary_author] += 1
    
    return diverse_recs


def enrich_recommendations(recommendations):
    """Add book details from MySQL"""
    enriched = []
    
    for rec in recommendations:
        isbn = rec["isbn"]
        
        with mysql_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT title, authors, publisher, publication_year
                FROM books WHERE isbn = :isbn
            """), {"isbn": isbn})
            book_row = result.fetchone()
        
        if not book_row:
            continue
        
        title, authors, publisher, pub_year = book_row
        
        # Get genres
        result = conn.execute(text("""
            SELECT rg.genre_name
            FROM books_subgenres bs
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE bs.isbn = :isbn
        """), {"isbn": isbn})
        genres = [row[0] for row in result.fetchall()]
        
        enriched.append({
            **rec,
            "title": title,
            "authors": authors,
            "publisher": publisher,
            "publication_year": pub_year,
            "genres": genres
        })
    
    return enriched


def display_recommendations(user_genres, recommendations, diversity_level):
    """Display diverse recommendations"""
    print("\n" + "=" * 80)
    print("🎨 DIVERSITY-AWARE RECOMMENDATIONS")
    print("=" * 80)
    
    print(f"\nDiversity Level: {diversity_level:.0%}")
    print(f"Your Reading Profile:")
    
    if user_genres:
        top_genres = sorted(user_genres.items(), key=lambda x: x[1], reverse=True)[:5]
        for genre, count in top_genres:
            print(f"  • {genre}: {count} books")
    
    familiar_count = sum(1 for r in recommendations if r.get("type") == "familiar")
    exploratory_count = sum(1 for r in recommendations if r.get("type") == "exploratory")
    
    print(f"\nRecommendation Mix:")
    print(f"  • Familiar genres: {familiar_count}")
    print(f"  • Exploratory genres: {exploratory_count}")
    
    print("\n" + "=" * 80)
    print("📚 DIVERSE RECOMMENDATIONS")
    print("=" * 80)
    
    for i, rec in enumerate(recommendations, 1):
        rec_type_emoji = "✅" if rec.get("type") == "familiar" else "🆕"
        print(f"\n{i}. {rec['title']} {rec_type_emoji}")
        print(f"   ISBN: {rec['isbn']}")
        print(f"   Authors: {rec['authors']}")
        print(f"   Genres: {', '.join(rec.get('genres', []))}")
        print(f"   Type: {rec.get('type', 'unknown').title()}")
        print(f"   Quality Score: {rec['score']:.2f}")
        
        if rec.get('metadata') and 'rating_metrics' in rec['metadata']:
            rm = rec['metadata']['rating_metrics']
            print(f"   Rating: {rm.get('r_avg', 'N/A')}/10 ({rm.get('r_count', 0)} ratings)")


def main():
    parser = argparse.ArgumentParser(description="Diversity-aware recommendations")
    parser.add_argument("--user_id", type=int, required=True, help="User ID")
    parser.add_argument("--limit", type=int, default=15, help="Number of recommendations")
    parser.add_argument("--diversity", type=float, default=0.5, 
                       help="Diversity level (0=familiar only, 1=exploratory only)")
    parser.add_argument("--max_per_author", type=int, default=2,
                       help="Maximum books per author")
    
    args = parser.parse_args()
    
    # Clamp diversity level
    diversity = max(0, min(1, args.diversity))
    
    try:
        print(f"\n🔍 Generating diverse recommendations for User {args.user_id}...")
        
        # Get user genre distribution
        user_genres = get_user_genre_distribution(args.user_id)
        
        if not user_genres:
            print(f"\n⚠️  User {args.user_id} has no rating history")
            print("Consider using cold-start recommendations instead")
            return
        
        # Get diverse recommendations
        recommendations = get_diverse_recommendations(args.user_id, diversity, args.limit * 2)
        
        if not recommendations:
            print("\n⚠️  No recommendations found")
            return
        
        # Ensure author diversity
        recommendations = ensure_author_diversity(recommendations, args.max_per_author)
        
        # Limit and enrich
        recommendations = recommendations[:args.limit]
        enriched = enrich_recommendations(recommendations)
        
        display_recommendations(user_genres, enriched, diversity)
    
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
