"""
Trending Books Recommendation System
Identifies and recommends books that are gaining momentum recently.
Uses recent ratings velocity, recency-weighted scores, and upward trends.
"""

from sqlalchemy import text

def get_trending_books_by_velocity(mysql_engine, min_recent_ratings=10, recent_window_pct=10, limit=20):
    """
    Identify trending books based on rating velocity.
    Velocity = (Recent Avg Rating * Recent Count) / Time Factor
    """
    with mysql_engine.connect() as conn:
        # Get max r_seq_book to define "recent"
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


def calculate_momentum_score(mysql_engine, isbn):
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


def get_user_preferred_genres(mysql_engine, user_id):
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


def filter_by_user_preferences(mysql_engine, mongo_db, trending_books, user_id, genre_filter=True):
    """Filter trending books by user's genre preferences"""
    if not genre_filter or not user_id:
        return trending_books
    
    user_genres = get_user_preferred_genres(mysql_engine, user_id)
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


def enrich_trending_books(mysql_engine, mongo_db, trending_books, calculate_momentum=True):
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
            momentum = calculate_momentum_score(mysql_engine, isbn)
        
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


