# Book Recommendation Project

> Hybrid MySQL + MongoDB recommendation system for books in amazon for the Advanced Database course.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

## Highlights
- **Hybrid persistence:** MySQL for transactional data, MongoDB for flexible user/book profiles.
- **Automated ingestion:** Kaggle download + split loaders for both databases.
- **Recommendation engine:** TruncatedSVD-based collaborative filtering with profile enrichment.
- **Interfaces:** CLI + FastAPI, ready for Dockerized MySQL/MongoDB.

## Repository map
- `src/bookrec/` – core loaders, models, API, CLI.
- `data/` – `raw/`, `interim/`, `processed/` (kept locally, ignored in git).
- `db/` – MySQL DDL, MongoDB schema docs.
- `docs/` – architecture notes, ER diagrams.
- `notebooks/` – EDA, cleaning, merging, DB loading.

## Quickstart
1. **Setup env**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Configure `.env` Example:**
   ```ini
   MYSQL_HOST=localhost
   MYSQL_PORT=3306
   MYSQL_USER=root
   MYSQL_PASSWORD=root
   MYSQL_DATABASE=bookrec
   MONGO_HOST=localhost
   MONGO_PORT=27017
   MONGO_DATABASE=bookrec
   ```

  **Note:** Ensure your `.env` file is correctly configured with your database credentials. Check also [.env.example](.env.example) for reference.

3. **Download + ingest**
   ```bash
   python -m bookrec.cli download-kaggle
   python -m bookrec.cli ingest --data-dir data/raw --drop-existing
   ```

## Usage
```bash
python -m bookrec.cli recommend --user-id 12345 --k 10
uvicorn bookrec.api.app:app --reload
```

## Roadmap
- Concurrency + transaction demos
- Query-optimization notebooks
- Scalability experiments (replicas, caching, sharding)

## Contributing
Open issues/PRs for improvements; follow course requirements for hybrid design.
