queries = {
    'Simple':
        {"MySQL":
            {'top_M_books':
                {'description': "Get top M books by rating count",
                 'variables': ['M'],
                 'query': """
                    SELECT
                    b.isbn, b.title, b.authors, 
                    COUNT(r.ratings) AS rating_count
                    FROM ratings r
                    JOIN books b ON r.isbn = b.isbn
                    GROUP BY b.isbn, b.title, b.authors
                    ORDER BY rating_count DESC
                    LIMIT :M;
                    """
                }
            },
        "MongoDB":
            {'top_M_price_range':
                {'description': "Find top M books within a specific price (H, L for high and low bound for price) range with good ratings (average rating >= 7).",
                 'query':
                    
                }
            }
        },
    'Complex':
        {"MySQL":
            {'content_based_recommendation':
                """
                SELECT *
                ....
                """
            },
        "MongoDB":
            {'content_based_recommendation':
                db.books.aggregate([
                    ...
                ])
        },
    'Hybrid':
        {'top_N_mysql':
            "MySQL":
                """
                    SELECT book FROM books
                    Where %s == cond 
                """,
            "MongoDB":
                db.books.find({%s: cond})
        }
}