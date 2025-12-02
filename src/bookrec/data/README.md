# bookrec.data

Data layer utilities.

- `load_raw.py` – robust loader for Kaggle CSVs (supports `Books/Users/Ratings.csv` and `BX-*` naming).
- `clean_transform.py` – column normalization, basic validation, and activity-based filtering.
- `db.py` – SQLAlchemy models for users, books, and ratings; session/engine helpers.
- `ingest_to_db.py` – create tables and bulk-ingest Pandas DataFrames into the database.

Notes:
- Default database is SQLite (`db/bookrec.db`). For PostgreSQL, set `DB_URL` in a `.env`.
- The SQL DDL + advanced queries are in the `db/` folder.
