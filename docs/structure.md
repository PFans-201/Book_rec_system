# Project structure

This repository is organized to separate concerns cleanly:

- `src/bookrec/` – Python package with all runtime code
  - `config.py` – central settings
  - `data/` – data loading, cleaning, ORM models, and ingestion
  - `models/` – recommenders (CF, content-based)
  - `evaluation/` – ranking metrics
  - `cli.py` – orchestration via Click
- `data/` – workspace for raw/interim/processed data
- `db/` – SQL schema and advanced query examples
- `docs/` – documentation
- `tests/` – quick tests for core parts

This layout supports both a database-first narrative (schema, SQL, ingestion) and a recommender narrative (modeling, evaluation, serving).
