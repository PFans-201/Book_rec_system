"""
Similar Books Recommendation System
Finds books similar to a given book based on genres, authors, and features.
Useful for "more like this" functionality.
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


def get_book_info(isbn):
    """Get book information from MySQL"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT title, authors, publisher, publication_year
            FROM books WHERE isbn = :isbn
        """), {"isbn": isbn})
        row = result.fetchone()
        
        if row:
            return {
                "isbn": isbn,
                "title": row[0],
                "authors": row[1],
                "publisher": row[2],
                "publication_year": row[3]
            }
    return None


def get_book_genres(isbn):
    """Get book's genres from MySQL"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rg.genre_name, sg.subgenre_name
            FROM books_subgenres bs
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE bs.isbn = :isbn
        """), {"isbn": isbn})
        
        root_genres = []
        subgenres = []
        for row in result.fetchall():
            root_genres.append(row[0])
            subgenres.append(row[1])
        
        return {
            "root_genres": list(set(root_genres)),
            "subgenres": list(set(subgenres))
        }


def parse_authors(authors_str):
    """Parse author string into list"""
    if not authors_str:
        return []
    
    # Remove brackets and quotes, split by comma
    authors = [a.strip().strip("'\"[]") for a in authors_str.split(",")]
    return [a for a in authors if a]


def find_similar_by_genres(isbn, genres, limit=100):
    """Find books with overlapping genres"""
    root_genres = genres["root_genres"]
    subgenres = genres["subgenres"]
    
    candidates = []
    
    if root_genres:
        with mysql_engine.connect() as conn:
            # Books sharing root genres
            result = conn.execute(text("""
                SELECT DISTINCT bs.isbn, COUNT(DISTINCT rg.genre_name) as genre_matches
                FROM books_subgenres bs
                JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
                JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
                WHERE rg.genre_name IN :genres AND bs.isbn != :isbn
                GROUP BY bs.isbn
                ORDER BY genre_matches DESC
                LIMIT :limit
            """), {"genres": tuple(root_genres), "isbn": isbn, "limit": limit})
            
            for row in result.fetchall():
                candidates.append({
                    "isbn": row[0],
                    "genre_matches": row[1],
                    "subgenre_matches": 0
                })
    
    # Enhance with subgenre matches
    if subgenres and candidates:
        for candidate in candidates:
            with mysql_engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COUNT(*)
                    FROM books_subgenres bs
                    JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
                    WHERE bs.isbn = :isbn AND sg.subgenre_name IN :subgenres
                """), {"isbn": candidate["isbn"], "subgenres": tuple(subgenres)})
                
                candidate["subgenre_matches"] = result.fetchone()[0] or 0
    
    return candidates


def calculate_similarity_score(target_book, candidate_isbn, genre_data):
    """Calculate comprehensive similarity score"""
    score = 0
    reasons = []
    
    # Genre matching (most important)
    genre_matches = genre_data.get("genre_matches", 0)
    subgenre_matches = genre_data.get("subgenre_matches", 0)
    
    genre_score = genre_matches * 15 + subgenre_matches * 10
    score += genre_score
    if genre_matches > 0:
        reasons.append(f"{genre_matches} shared genres (+{genre_matches * 15})")
    if subgenre_matches > 0:
        reasons.append(f"{subgenre_matches} shared subgenres (+{subgenre_matches * 10})")
    
    # Get candidate book info
    candidate_info = get_book_info(candidate_isbn)
    if not candidate_info:
        return score, reasons
    
    # Author matching
    target_authors = parse_authors(target_book["authors"])
    candidate_authors = parse_authors(candidate_info["authors"])
    
    author_overlap = len(set(target_authors).intersection(set(candidate_authors)))
    if author_overlap > 0:
        author_score = author_overlap * 20
        score += author_score
        reasons.append(f"shared author (+{author_score})")
    
    # Publisher matching (minor)
    if target_book["publisher"] == candidate_info["publisher"]:
        score += 5
        reasons.append("same publisher (+5)")
    
    # Publication year proximity (prefer similar era)
    if target_book["publication_year"] and candidate_info["publication_year"]:
        year_diff = abs(int(target_book["publication_year"]) - int(candidate_info["publication_year"]))
        if year_diff <= 3:
            score += 5
            reasons.append("similar publication year (+5)")
    
    # Get quality scores from MongoDB
    target_meta = mongo_db.books_metadata.find_one({"_id": target_book["isbn"]})
    candidate_meta = mongo_db.books_metadata.find_one({"_id": candidate_isbn})
    
    # Quality bonus (prefer highly rated books)
    if candidate_meta and "rating_metrics" in candidate_meta:
        rm = candidate_meta["rating_metrics"]
        quality = rm.get("rating_score", 0)
        
        if quality >= 7:
            score += quality * 2
            reasons.append(f"high quality (+{quality * 2:.1f})")
    
    return score, reasons


def find_similar_books(isbn, limit=10):
    """Find books similar to the given ISBN"""
    
    # Get target book info
    target_book = get_book_info(isbn)
    if not target_book:
        return None, []
    
    # Get target book genres
    genres = get_book_genres(isbn)
    if not genres["root_genres"]:
        return target_book, []
    
    # Find candidates by genre
    candidates = find_similar_by_genres(isbn, genres, limit=limit * 10)
    
    if not candidates:
        return target_book, []
    
    # Calculate similarity scores
    scored = []
    for candidate in candidates:
        score, reasons = calculate_similarity_score(
            target_book, 
            candidate["isbn"],
            candidate
        )
        
        scored.append({
            "isbn": candidate["isbn"],
            "similarity_score": score,
            "reasons": reasons
        })
    
    # Sort by score
    scored.sort(key=lambda x: x["similarity_score"], reverse=True)
    return target_book, scored[:limit]


def enrich_recommendations(recommendations):
    """Add book details from MySQL and MongoDB"""
    enriched = []
    
    for rec in recommendations:
        isbn = rec["isbn"]
        
        # Get book details from MySQL
        book_info = get_book_info(isbn)
        if not book_info:
            continue
        
        # Get metadata from MongoDB
        book_meta = mongo_db.books_metadata.find_one({"_id": isbn})
        
        # Get genres
        genres = get_book_genres(isbn)
        
        enriched.append({
            **rec,
            **book_info,
            "genres": genres["root_genres"],
            "metadata": book_meta
        })
    
    return enriched


def display_recommendations(target_book, recommendations):
    """Display similar book recommendations"""
    print("\n" + "=" * 80)
    print("🔍 SIMILAR BOOKS")
    print("=" * 80)
    
    print(f"\nTarget Book:")
    print(f"  Title: {target_book['title']}")
    print(f"  ISBN: {target_book['isbn']}")
    print(f"  Authors: {target_book['authors']}")
    print(f"  Publisher: {target_book['publisher']}")
    print(f"  Year: {target_book['publication_year']}")
    
    print("\n" + "=" * 80)
    print("📚 BOOKS SIMILAR TO THIS")
    print("=" * 80)
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['title']}")
        print(f"   ISBN: {rec['isbn']}")
        print(f"   Authors: {rec['authors']}")
        print(f"   📊 Similarity Score: {rec['similarity_score']:.1f}")
        print(f"   Reasons:")
        for reason in rec['reasons']:
            print(f"     • {reason}")
        
        print(f"   Genres: {', '.join(rec.get('genres', []))}")
        
        if rec.get('metadata') and 'rating_metrics' in rec['metadata']:
            rm = rec['metadata']['rating_metrics']
            print(f"   Rating: {rm.get('r_avg', 'N/A')}/10 ({rm.get('r_count', 0)} ratings)")


def main():
    parser = argparse.ArgumentParser(description="Find books similar to a given book")
    parser.add_argument("--isbn", type=str, required=True, help="Target book ISBN")
    parser.add_argument("--limit", type=int, default=10, help="Number of similar books")
    
    args = parser.parse_args()
    
    try:
        print(f"\n🔍 Finding books similar to ISBN: {args.isbn}...")
        
        target_book, recommendations = find_similar_books(args.isbn, limit=args.limit)
        
        if not target_book:
            print(f"\n⚠️  Book with ISBN {args.isbn} not found")
            return
        
        if not recommendations:
            print(f"\n⚠️  No similar books found for '{target_book['title']}'")
            return
        
        enriched = enrich_recommendations(recommendations)
        display_recommendations(target_book, enriched)
    
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()
