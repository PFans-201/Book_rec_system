# SQL design and queries

## Schema highlights
- `users(user_id PK, age, location)`
- `books(isbn PK, title, author, year, publisher)`
- `ratings(id PK, user_id FK, isbn FK, rating, UNIQUE(user_id,isbn))`

Indexes:
- `books(author)`, `books(title)` – speed up lookups and text search filters
- `ratings(user_id)`, `ratings(isbn)`, `ratings(rating)` – common join and aggregation paths

SQLite adds:
- `vw_book_stats` view for average rating and counts
- `trg_ratings_bound` trigger ensuring `rating` ∈ [0,10]

## Example analytics (PostgreSQL)
See `db/queries_postgres.sql` for:
- Top-N books by explicit rating with minimum support
- Activity distribution with window functions (percentiles)
- Item co-occurrence/Jaccard similarity for similar-books discovery
- Materialized-view sketch for popularity

## Performance notes
- Ensure `ANALYZE` is run after bulk loads (Postgres) to update stats.
- For heavy joins on large ratings, consider partitioning or clustering by `user_id` or `isbn` (Postgres).
- Consider trigram indexes (pg_trgm) for fuzzy title search if needed.
