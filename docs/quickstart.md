# Quick Start Examples

This file gives copy-paste-ready commands to get you up and running.

## 1) Install dependencies and the package

```bash
# Activate your virtualenv
source db_venv/bin/activate  # Linux/Mac
# or on Windows: db_venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install bookrec in editable mode
pip install -e .
```

## 2) Download Kaggle dataset (auto)

```bash
python -m bookrec.cli download-kaggle
```

This fetches `Books.csv`, `Users.csv`, and `Ratings.csv` into `data/raw/`.

## 3) Ingest into the database

```bash
python -m bookrec.cli ingest --data-dir data/raw --drop-existing
```

## 4) Get top-10 recommendations for a user

```bash
# Replace 12345 with a real user_id from your data
python -m bookrec.cli recommend --user-id 12345 --k 10
```

## 5) Run the API locally

```bash
uvicorn bookrec.api.app:app --reload
```


## 6) Run tests

```bash
pytest -v
```

All tests should pass after installing dependencies and the package.

## Tips
- Check `docs/er_diagram.md` for the ER model and `db/advanced_queries.sql` for Postgres advanced queries (stored procedures, recursive CTEs, materialized views).
