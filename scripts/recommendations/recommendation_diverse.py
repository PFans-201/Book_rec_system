"""
Diversity-Aware Recommendation System
Provides diverse recommendations across multiple genres and authors.
Balances personalization with exploration and variety.
"""

from sqlalchemy import text
from collections import defaultdict, Counter

def get_user_genre_distribution(mysql_engine, user_id):
    """Get distribution of genres in user's reading history"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT rg.root_name, COUNT(*) as count
            FROM ratings r
            JOIN book_root_genres brg ON r.isbn = brg.isbn
            JOIN root_genres rg ON brg.root_id = rg.root_id
            WHERE r.user_id = :user_id
            GROUP BY rg.root_name
            ORDER BY count DESC
        """), {"user_id": user_id})
        
        genres = {}
        for row in result.fetchall():
            genres[row[0]] = row[1]
        
        return genres


def get_user_author_distribution(mysql_engine, user_id):
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


def identify_underexplored_genres(mysql_engine, user_genres, top_n=5):
    """Identify genres user hasn't explored much"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT root_name FROM root_genres
        """))
        all_genres = [row[0] for row in result.fetchall()]
    
    # Find genres with 0 or low count
    underexplored = []
    for genre in all_genres:
        count = user_genres.get(genre, 0)
        if count < 3:  # Less than 3 books in this genre
            underexplored.append(genre)
    
    return underexplored[:top_n]


def get_diverse_recommendations(mysql_engine, mongo_db, user_id, diversity_level=0.5, limit=20):
    """
    Get diverse recommendations
    diversity_level: 0 = only familiar, 1 = only exploratory, 0.5 = balanced
    """
    
    # Get user's current distribution
    user_genres = get_user_genre_distribution(mysql_engine, user_id)
    user_authors = get_user_author_distribution(mysql_engine, user_id)
    
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
                SELECT DISTINCT brg.isbn
                FROM book_root_genres brg
                JOIN root_genres rg ON brg.root_id = rg.root_id
                WHERE rg.root_name IN :genres
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
        underexplored = identify_underexplored_genres(mysql_engine, user_genres)
        
        if underexplored:
            with mysql_engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT DISTINCT brg.isbn
                    FROM book_root_genres brg
                    JOIN root_genres rg ON brg.root_id = rg.root_id
                    WHERE rg.root_name IN :genres
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


def enrich_recommendations(mysql_engine, recommendations):
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
                SELECT rg.root_name
                FROM book_root_genres brg
                JOIN root_genres rg ON brg.root_id = rg.root_id
                WHERE brg.isbn = :isbn
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


