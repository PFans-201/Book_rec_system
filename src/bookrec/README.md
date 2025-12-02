# bookrec package

Core Python package for the project.

- `config.py` – central settings (paths, DB URL, thresholds) with `.env` support.
- `data/` – load Kaggle CSVs, clean and normalize data, ORM models, and DB ingestion helpers.
- `models/` – baseline recommenders: collaborative filtering and content-based.
- `evaluation/` – ranking metrics for offline evaluation.
- `api/` – FastAPI app exposing recommendation endpoints.
- `cli.py` – Click CLI orchestrating the main flows (ingestion, recommend).
