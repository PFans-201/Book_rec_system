"""
Similar Books Recommendation System
Finds books similar to a given book based on genres, authors, and features.
Useful for "more like this" functionality.
"""

from sqlalchemy import text


def get_book_info(mysql_engine, isbn):
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


def get_book_genres(mysql_engine, isbn):
    """Get book's genres from MySQL"""
    with mysql_engine.connect() as conn:
        # Get root genres
        result_root = conn.execute(text("""
            SELECT rg.root_name
            FROM book_root_genres brg
            JOIN root_genres rg ON brg.root_id = rg.root_id
            WHERE brg.isbn = :isbn
        """), {"isbn": isbn})
        root_genres = [row[0] for row in result_root.fetchall()]

        # Get subgenres
        result_sub = conn.execute(text("""
            SELECT sg.subgenre_name
            FROM book_subgenres bs
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            WHERE bs.isbn = :isbn
        """), {"isbn": isbn})
        subgenres = [row[0] for row in result_sub.fetchall()]

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


def find_similar_by_genres(mysql_engine, isbn, genres, limit=100):
    """Find books with overlapping genres"""
    root_genres = genres["root_genres"]
    subgenres = genres["subgenres"]

    candidates = []

    if root_genres:
        with mysql_engine.connect() as conn:
            # Books sharing root genres
            result = conn.execute(text("""
                SELECT DISTINCT brg.isbn, COUNT(DISTINCT rg.root_name) as genre_matches
                FROM book_root_genres brg
                JOIN root_genres rg ON brg.root_id = rg.root_id
                WHERE rg.root_name IN :genres AND brg.isbn != :isbn
                GROUP BY brg.isbn
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
                    FROM book_subgenres bs
                    JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
                    WHERE bs.isbn = :isbn AND sg.subgenre_name IN :subgenres
                """), {"isbn": candidate["isbn"], "subgenres": tuple(subgenres)})

                candidate["subgenre_matches"] = result.fetchone()[0] or 0

    return candidates


def calculate_similarity_score(mysql_engine, mongo_db, target_book, candidate_isbn, genre_data):
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
    candidate_info = get_book_info(mysql_engine, candidate_isbn)
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


def find_similar_books(mysql_engine, mongo_db, isbn, limit=10):
    """Find books similar to the given ISBN"""
    
    # Get target book info
    target_book = get_book_info(mysql_engine, isbn)
    if not target_book:
        return None, []
    
    # Get target book genres
    genres = get_book_genres(mysql_engine, isbn)
    if not genres["root_genres"]:
        return target_book, []
    
    # Find candidates by genre
    candidates = find_similar_by_genres(mysql_engine, isbn, genres, limit=limit * 10)
    
    if not candidates:
        return target_book, []
    
    # Calculate similarity scores
    scored = []
    for candidate in candidates:
        score, reasons = calculate_similarity_score(
            mysql_engine,
            mongo_db,
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


def enrich_recommendations(mysql_engine, mongo_db, recommendations):
    """Add book details from MySQL and MongoDB"""
    enriched = []
    
    for rec in recommendations:
        isbn = rec["isbn"]
        
        # Get book details from MySQL
        book_info = get_book_info(mysql_engine, isbn)
        if not book_info:
            continue
        
        # Get metadata from MongoDB
        book_meta = mongo_db.books_metadata.find_one({"_id": isbn})
        
        # Get genres
        genres = get_book_genres(mysql_engine, isbn)
        enriched.append({
            **rec,
            **book_info,
            "genres": genres["root_genres"],
            "metadata": book_meta
        })

    return enriched


