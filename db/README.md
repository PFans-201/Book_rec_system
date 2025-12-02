# db/

SQL artifacts and database notes.

- `schema.sql` – SQLite DDL with tables, indexes, a view, and a trigger for rating bounds.
- `queries_postgres.sql` – advanced query examples for PostgreSQL (windows, Jaccard co-occurrence, materialized view sketch).
- `advanced_queries.sql` – stored procedure for upserts, recursive CTE for user chains, materialized view for top books, window functions, and lateral joins.

Default runtime DB is SQLite via SQLAlchemy; switch to Postgres by setting `DB_URL` in `.env`.


+-------------------+           +-------------------+           +-----------------------+
|      USERS        |           |     RATINGS       |           |       BOOKS           |
+-------------------+           +-------------------+           +-----------------------+
| * user_id (PK)    |<--+    +--| * user_id (FK)    |           | * isbn (PK)           |
|   location        |           | * isbn (FK)       |           |   title               |
|   age             |           |  book_rating     |           |   author              |
+-------------------+   |    |  +-------------------+           |   year_of_publication |
