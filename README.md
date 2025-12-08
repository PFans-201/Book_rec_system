# Book Recommendation Project

> Hybrid MySQL + MongoDB recommendation system for books in amazon for the Advanced Database course.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

## Highlights
- **Hybrid persistence:** MySQL for transactional data, MongoDB for flexible user/book profiles.
- **Automated ingestion:** Kaggle download + split loaders for both databases.
- **Recommendation engine:** Content-based, collaborative, geographic and demographic recommendations. Ranging from simple and complex queries performed within the same database using one or multiple data sources (tables/collections), respectively, to 

## Repository map
- `data/` – `raw/`, `interim/`, `processed/` (most kept locally, ignored in git).
- `db/` – MySQL table schemas, MongoDB schema docs.
- `docs/` – professor's guideline and architecture notes.
- `notebooks/` – EDA, cleaning, merging, DB loading, etc.

## Quickstart
1. **Setup env**
   ```bash
   python -m venv .venv
   # for Linux/Mac
   source .venv/bin/activate

   # for Windows
   .venv\Scripts\activate

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
Open the [notebooks](notebooks/) in order to:  
- [0.](notebooks/0_download_plus_EDA.ipynb) download and explore original datasets;
- [1.](notebooks/1_preprocessing_data.ipynb) Preprocess datasets before merging;
- [2.](notebooks/2_merge.ipynb) Merging of datasets and final cleaning;
- [3.](notebooks/3_db__data_loading.ipynb) Load data into MySQL and MongoDB databases.
- [4.](notebooks/4_recommendations_queries.ipynb) Generate recommendations for a user.
- TODO - rest of sections: concurency testing; performance analysis and optimization


## Queries
- [queries.md](scripts/queries.md): contains a description of available queries and their usage.
- [Query_execution.md](scripts/queries/Query_execution.md): contains a description of how to execute the queries in the scripts folder.
- [query_helper.py](scripts/queries/query_helper.py): contains query definitions for both MySQL and MongoDB, as well as functions to help in the queries' execution, performance and query plan analysis.

## Contributing
Open issues for improvements; follow course requirements for hybrid design.
