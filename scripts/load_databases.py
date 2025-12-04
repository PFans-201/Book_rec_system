"""
Data Loading Pipeline: CSV → MySQL + MongoDB
Loads processed data into hybrid database architecture following the defined schema.
"""

from pathlib import Path
from dotenv import load_dotenv
import os
import pandas as pd
from sqlalchemy import create_engine, text
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import numpy as np
from typing import Dict, List, Optional, Any
import warnings
from tqdm import tqdm
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================

# Get the project root directory (parent of scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FINAL_DIR = PROJECT_ROOT / "data/final"
SCHEMA_PATH = PROJECT_ROOT / "db/mysql_schema.sql"
ENV_PATH = PROJECT_ROOT / ".env"

# ----------------- Load environment -----------------
# Specify exact path to .env file
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    print(f"✓ Loaded environment from: {ENV_PATH}")
else:
    print(f"⚠️  .env file not found at: {ENV_PATH}")
    print(f"   Current working directory: {Path.cwd()}")

# Load credentials from environment
db_name = os.getenv("DB_NAME", "bookrec")  # Provide default
host = os.getenv("HOST", "localhost")  # Provide default

mdb_port = os.getenv("MDB_PORT", "27017")  # Provide default
mdb_user = os.getenv("MDB_USER")
mdb_password = os.getenv("MDB_PASSWORD")
mdb_cluster = os.getenv("MDB_CLUSTER")  # e.g., "bookreccluster.xxxxx.mongodb.net"
mdb_appname = os.getenv("MDB_APPNAME", "Cluster0")  # Provide default
mdb_use_atlas = os.getenv("MDB_USE_ATLAS", "false").lower() == "true"  # Flag for Atlas vs local

msql_user = os.getenv("MSQL_USER")
msql_password = os.getenv("MSQL_PASSWORD")
msql_port = os.getenv("MSQL_PORT", "3306")

# Validate credentials
if not all([msql_user, msql_password]):
    print("⚠️  MySQL credentials not found in environment!")
    print(f"   MSQL_USER: {msql_user}")
    print(f"   MSQL_PASSWORD: {'***' if msql_password else 'NOT SET'}")
    raise ValueError("MySQL credentials (MSQL_USER, MSQL_PASSWORD) must be set in .env file")

if not all([mdb_user, mdb_password]):
    print("⚠️  MongoDB credentials not found in environment!")
    print(f"   MDB_USER: {mdb_user}")
    print(f"   MDB_PASSWORD: {'***' if mdb_password else 'NOT SET'}")
    raise ValueError("MongoDB credentials (MDB_USER, MDB_PASSWORD) must be set in .env file")

if mdb_use_atlas and not mdb_cluster:
    print("⚠️  MDB_USE_ATLAS is true but MDB_CLUSTER not set!")
    raise ValueError("MDB_CLUSTER must be set when MDB_USE_ATLAS=true")

# Database connections - USE ENVIRONMENT VARIABLES
MYSQL_CONFIG = {
    'host': host,
    'user': msql_user,
    'password': msql_password,
    'database': db_name,
    'port': int(msql_port),
}

# MongoDB Configuration (Atlas or Local)
if mdb_use_atlas:
    # MongoDB Atlas connection
    MONGODB_URI = f"mongodb+srv://{mdb_user}:{mdb_password}@{mdb_cluster}/?retryWrites=true&w=majority&appName={mdb_appname}"
    MONGODB_USE_SERVER_API = True
    print(f"✓ Using MongoDB Atlas: {mdb_cluster}")
else:
    # Local MongoDB connection
    MONGODB_URI = f"mongodb://{mdb_user}:{mdb_password}@{host}:{mdb_port}/"
    MONGODB_USE_SERVER_API = False
    print(f"✓ Using Local MongoDB: {host}:{mdb_port}")

MONGODB_DATABASE = db_name

# Data loading configuration
DATA_LOADING_CONFIG = {
    'MySQL': {
        'tables': {
            'root_genres': {
                'df_name': 'root_genres',
                'columns': ['root_id', 'root_name']
            },
            'subgenres': {
                'df_name': 'subgenres',
                'columns': ['subgenre_id', 'subgenre_name', 'root_id']
            },
            'users': {
                'df_name': 'users',
                'columns': ['user_id', 'age', 'age_group', 'gender', 'location', 
                           'country', 'latitude', 'longitude', 'has_ratings', 'has_preferences'],
                'rename': {'latitude': 'loc_latitude', 'longitude': 'loc_longitude'}  # Match schema
            },
            'books': {
                'df_name': 'books',
                'columns': ['isbn', 'title', 'authors', 'publication_year', 'publisher']
            },
            'book_root_genres': {
                'df_name': 'book_root_genres',
                'columns': ['isbn', 'root_id']
            },
            'book_subgenres': {
                'df_name': 'book_subgenres',
                'columns': ['isbn', 'subgenre_id']
            },
            'ratings': {
                'df_name': 'ratings',
                'columns': ['user_id', 'isbn', 'rating', 'r_seq_user', 'r_seq_book', 'r_cat'],
                # Note: ratings_seq is AUTO_INCREMENT, so we exclude it from insertion
            }
        },
        # Insertion order (respects foreign keys)
        'insert_order': ['root_genres', 'subgenres', 'users', 'books', 
                        'book_root_genres', 'book_subgenres', 'ratings']
    },
    'MongoDB': {
        'collections': {
            'books_metadata': {
                'df_name': 'books',
                'id_field': 'isbn',
                'fields': {
                    'extra_metadata': ['price_usd', 'genre', 'root_genres', 'subgenres', 
                                      'regional_tags', 'image_alternative', 'previewlink', 
                                      'infolink', 'image_url_s', 'image_url_m', 
                                      'image_url_l', 'description'],
                    'rating_metrics': ['rating_score', 'r_category', 'r_total', 
                                      'r_count', 'r_avg', 'r_std'],
                    'popularity_metrics': ['recent_count', 'popularity', 'popularity_cat']
                }
            },
            'users_profiles': {
                'df_name': 'users',
                'id_field': 'user_id',
                'fields': {
                    'profile': ['reader_level', 'critic_profile', 'mean_rating', 
                               'median_rating', 'std_rating', 'total_ratings', 
                               'total_books', 'explicit_ratings', 'has_ratings', 
                               'has_preferences'],
                    'preferences': ['pref_pub_year', 'pref_root_genres', 'pref_subgenres', 
                                   'pref_authors', 'pref_publisher', 'pref_price_min', 
                                   'pref_price_max', 'pref_price_avg']
                }
            }
        }
    }
}

# ============================================================================
# DATA LOADING
# ============================================================================

def load_all_csvs(data_dir: Path) -> Dict[str, pd.DataFrame]:
    """Load all CSV files from the final data directory"""
    print("=" * 80)
    print("📂 LOADING CSV FILES")
    print("=" * 80)
    
    csv_files = list(data_dir.glob("*.csv"))
    dataframes = {}
    
    for f in csv_files:
        df = pd.read_csv(f, sep=",", low_memory=False)
        # Clean data: replace empty strings and inf with None/NaN
        df = df.replace('', np.nan)
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        
        dataframes[f.stem] = df
        print(f"✓ Loaded {f.stem}: {len(df):,} rows, {len(df.columns)} columns")
    
    print("=" * 80 + "\n")
    return dataframes


# ============================================================================
# MYSQL LOADING
# ============================================================================

def execute_schema(schema_path: Path, engine: Any) -> None:
    """Execute MySQL schema DDL file using SQLAlchemy"""
    print("=" * 80)
    print("🔧 EXECUTING MYSQL SCHEMA")
    print("=" * 80)
    
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    
    # Split by delimiter changes and statements
    statements = []
    current_statement = []
    delimiter = ';'
    
    for line in schema_sql.split('\n'):
        line = line.strip()
        
        if line.upper().startswith('DELIMITER'):
            if current_statement:
                statements.append('\n'.join(current_statement))
                current_statement = []
            delimiter = line.split()[-1]
            continue
        
        if not line or line.startswith('--'):
            continue
        
        current_statement.append(line)
        
        if line.endswith(delimiter) and delimiter != '$$':
            statements.append('\n'.join(current_statement))
            current_statement = []
    
    if current_statement:
        statements.append('\n'.join(current_statement))
    
    # Execute statements with proper error handling
    failed_statements = []
    with engine.connect() as conn:
        for i, stmt in enumerate(statements):
            stmt = stmt.strip().rstrip(';').rstrip('$$')
            if stmt:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                    # Only show progress for significant operations
                    if 'CREATE TABLE' in stmt.upper() or 'CREATE TRIGGER' in stmt.upper():
                        table_name = stmt.split()[2] if len(stmt.split()) > 2 else 'unknown'
                        print(f"✓ Created: {table_name}")
                except Exception as e:
                    error_msg = str(e).split('\n')[0]  # First line only
                    failed_statements.append((i+1, error_msg, stmt[:80]))
    
    if failed_statements:
        print(f"\n⚠️  {len(failed_statements)} statements failed:")
        for stmt_num, error, sql_preview in failed_statements:
            print(f"  Statement {stmt_num}: {error}")
            print(f"    SQL: {sql_preview}...")
    else:
        print(f"✓ All {len(statements)} statements executed successfully")
    
    print("=" * 80 + "\n")


def _table_exists(conn: Any, db_name: str, table_name: str) -> bool:
    """Check if a table exists in the given database."""
    res = conn.execute(text(
        """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = :db AND table_name = :tbl
        """
    ), {"db": db_name, "tbl": table_name}).scalar()
    return bool(res)


def _fk_exists(conn: Any, db_name: str, table_name: str, ref_table: str) -> bool:
    """Check if a foreign key exists from table_name to ref_table."""
    res = conn.execute(text(
        """
        SELECT COUNT(*)
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = :db
          AND TABLE_NAME = :tbl
          AND REFERENCED_TABLE_NAME = :ref
        """
    ), {"db": db_name, "tbl": table_name, "ref": ref_table}).scalar()
    return bool(res)


def verify_mysql_schema(engine: Any, db_name: str) -> None:
    """Verify critical tables and foreign keys exist before inserting data.

    Prevents pandas.to_sql from implicitly creating unconstrained tables.
    """
    print("=" * 80)
    print("✅ VERIFYING MYSQL SCHEMA")
    print("=" * 80)
    required_tables = [
        "users", "books", "ratings", "root_genres", "subgenres",
        "book_root_genres", "book_subgenres"
    ]
    with engine.connect() as conn:
        # Tables must exist
        missing = [t for t in required_tables if not _table_exists(conn, db_name, t)]
        if missing:
            raise RuntimeError(f"Schema verification failed. Missing tables: {missing}")

        # Check essential foreign keys
        fk_checks = [
            ("ratings", "users"),
            ("ratings", "books"),
            ("book_root_genres", "books"),
            ("book_root_genres", "root_genres"),
            ("book_subgenres", "books"),
            ("book_subgenres", "subgenres"),
            ("subgenres", "root_genres")
        ]
        fk_missing = [
            f"{src}->{dst}" for (src, dst) in fk_checks if not _fk_exists(conn, db_name, src, dst)
        ]
        if fk_missing:
            raise RuntimeError(
                "Schema verification failed. Missing foreign keys: " + ", ".join(fk_missing)
            )
        print("✓ All required tables and foreign keys are present")
    print("=" * 80 + "\n")


def clean_dataframe_for_mysql(df: pd.DataFrame, columns: List[str], 
                               rename_map: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """Prepare dataframe for MySQL insertion"""
    df_clean = df[columns].copy()
    
    # Fix: Check if rename_map is not None before using it
    if rename_map is not None:
        df_clean = df_clean.rename(columns=rename_map)
    
    # Replace NaN with None for proper SQL NULL handling
    df_clean = df_clean.replace({np.nan: None})
    
    # Convert numpy types to Python native types
    for col in df_clean.columns:
        if df_clean[col].dtype == np.int64:
            df_clean[col] = df_clean[col].astype('Int64')  # Nullable integer
        elif df_clean[col].dtype == np.float64:
            # Convert to object dtype to allow None values
            df_clean[col] = df_clean[col].astype(object)
        elif df_clean[col].dtype == bool:
            df_clean[col] = df_clean[col].astype(int)
    
    # Final pass: ensure all NaN/NaT are None
    df_clean = df_clean.where(pd.notna(df_clean), None)
    
    return df_clean


def load_mysql_data(dataframes: Dict[str, pd.DataFrame], config: Dict[str, Any], 
                    mysql_engine: Any) -> None:
    """Load data into MySQL following insertion order with optimized bulk inserts"""
    print("=" * 80)
    print("📊 LOADING DATA INTO MYSQL")
    print("=" * 80)
    
    mysql_config = config['MySQL']
    insert_order = mysql_config['insert_order']
    tables_config = mysql_config['tables']
    
    # Truncate all tables first to handle repeated runs cleanly
    print("\n🗑️  Truncating existing data...")
    with mysql_engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table_name in tqdm(reversed(insert_order), desc="Clearing tables", total=len(insert_order), leave=False):
            try:
                conn.execute(text(f"TRUNCATE TABLE {table_name}"))
            except Exception as e:
                pass  # Table might not exist yet
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()
    print("✓ Tables cleared\n")
    
    import time
    total_start = time.time()
    
    for table_name in insert_order:
        table_config = tables_config[table_name]
        df_name = table_config['df_name']
        columns = table_config['columns']
        rename_map = table_config.get('rename')
        
        if df_name not in dataframes:
            print(f"⚠️  Skipping {table_name}: DataFrame '{df_name}' not found")
            continue
        
        table_start = time.time()
        
        df_to_insert = clean_dataframe_for_mysql(
            dataframes[df_name], 
            columns, 
            rename_map
        )
        
        # Exclude AUTO_INCREMENT columns
        if table_name == 'ratings':
            insert_columns = [col for col in df_to_insert.columns if col != 'ratings_seq']
            df_to_insert = df_to_insert[insert_columns]
        
        row_count = len(df_to_insert)
        
        try:
            # Use optimized bulk insert with larger chunks
            # Disable autocommit for faster inserts
            with mysql_engine.connect() as conn:
                conn.execute(text("SET autocommit=0"))
                conn.execute(text("SET unique_checks=0"))
                conn.execute(text("SET foreign_key_checks=0"))
                
                # Use LOAD DATA LOCAL INFILE simulation via executemany
                chunk_size = 5000  # Much larger chunks for better performance
                
                # Progress bar for insertion
                with tqdm(total=row_count, desc=f"📋 {table_name:20s}", 
                         unit="rows", unit_scale=True, ncols=100) as pbar:
                    
                    for start_idx in range(0, row_count, chunk_size):
                        end_idx = min(start_idx + chunk_size, row_count)
                        chunk = df_to_insert.iloc[start_idx:end_idx]
                        
                        # Build INSERT statement
                        cols = list(chunk.columns)
                        placeholders = ', '.join([f':{col}' for col in cols])
                        insert_sql = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})"
                        
                        # Convert chunk to list of dicts, ensuring None for NULL values
                        records = []
                        for _, row in chunk.iterrows():
                            record = {}
                            for col in cols:
                                val = row[col]
                                # Convert pandas NA types to None
                                if pd.isna(val):
                                    record[col] = None
                                elif isinstance(val, (np.integer, np.floating)):
                                    # Convert numpy types to Python types
                                    record[col] = val.item() if hasattr(val, 'item') else val
                                else:
                                    record[col] = val
                            records.append(record)
                        
                        # Execute batch
                        conn.execute(text(insert_sql), records)
                        pbar.update(len(chunk))
                
                conn.execute(text("COMMIT"))
                conn.execute(text("SET unique_checks=1"))
                conn.execute(text("SET foreign_key_checks=1"))
                conn.execute(text("SET autocommit=1"))
            
            elapsed = time.time() - table_start
            tqdm.write(f"  ✅ {row_count:,} rows in {elapsed:.1f}s ({row_count/elapsed:,.0f} rows/s)")
            
        except Exception as e:
            elapsed = time.time() - table_start
            error_msg = str(e).split('[SQL:')[0].strip() if '[SQL:' in str(e) else str(e)
            error_msg = error_msg.split('\n')[0][:100]  # First line, max 100 chars
            tqdm.write(f"  ❌ {table_name} failed after {elapsed:.1f}s")
            tqdm.write(f"     Error: {error_msg}")
    
    total_elapsed = time.time() - total_start
    print(f"\n✅ MySQL loading complete in {total_elapsed:.1f}s")
    print("=" * 80 + "\n")


# ============================================================================
# MONGODB LOADING
# ============================================================================

def build_mongo_document(row: pd.Series, config: Dict[str, List[str]]) -> Dict[str, Any]:
    """Build a MongoDB document from a DataFrame row"""
    doc: Dict[str, Any] = {}
    
    for category, fields in config.items():
        category_data: Dict[str, Any] = {}
        for field in fields:
            if field in row.index and pd.notna(row[field]):
                value = row[field]
                
                # Fix: Use numpy.integer and numpy.floating base classes
                if isinstance(value, np.integer):
                    value = int(value)
                elif isinstance(value, np.floating):
                    value = float(value)
                elif isinstance(value, np.bool_):
                    value = bool(value)
                elif pd.isna(value):
                    continue
                
                category_data[field] = value
        
        if category_data:
            doc[category] = category_data
    
    return doc


def load_mongodb_data(dataframes: Dict[str, pd.DataFrame], config: Dict[str, Any], 
                      mongo_db: Any) -> None:
    """Load data into MongoDB collections with optimized batch inserts"""
    print("=" * 80)
    print("📊 LOADING DATA INTO MONGODB")
    print("=" * 80)

    import time
    mongodb_config = config['MongoDB']
    collections_config = mongodb_config['collections']
    
    total_start = time.time()
    
    for collection_name, coll_config in collections_config.items():
        df_name = coll_config['df_name']
        id_field = coll_config['id_field']
        fields_config = coll_config['fields']
        
        if df_name not in dataframes:
            print(f"⚠️  Skipping {collection_name}: DataFrame '{df_name}' not found")
            continue
        
        coll_start = time.time()
        
        df = dataframes[df_name]
        collection = mongo_db[collection_name]
        
        # Drop collection if exists (for clean repeated runs)
        if collection_name in mongo_db.list_collection_names():
            collection.drop()
        
        # Build documents with larger batches and progress bar
        documents = []
        batch_size = 5000  # Larger batches for MongoDB
        total_rows = len(df)
        
        # Progress bar for MongoDB insertion
        with tqdm(total=total_rows, desc=f"📋 {collection_name:20s}", 
                 unit="docs", unit_scale=True, ncols=100) as pbar:
            
            for idx, row in df.iterrows():
                doc = build_mongo_document(row, fields_config)
                
                if doc:
                    doc['_id'] = row[id_field]
                    documents.append(doc)
                
                # Batch insert
                if len(documents) >= batch_size:
                    try:
                        collection.insert_many(documents, ordered=False)
                    except Exception as e:
                        # Handle duplicate key errors gracefully
                        pass
                    pbar.update(len(documents))
                    documents = []
            
            # Insert remaining documents
            if documents:
                try:
                    collection.insert_many(documents, ordered=False)
                except Exception as e:
                    pass
                pbar.update(len(documents))
        
        doc_count = collection.count_documents({})
        elapsed = time.time() - coll_start
        tqdm.write(f"  ✅ {doc_count:,} docs in {elapsed:.1f}s ({doc_count/elapsed:,.0f} docs/s)")
        
        # Show sample document structure (find one with maximum fields)
        try:
            pipeline = [
                {"$project": {"doc": "$$ROOT", "keyCount": {"$size": {"$objectToArray": "$$ROOT"}}}},
                {"$sort": {"keyCount": -1}},
                {"$limit": 1}
            ]
            rich_sample = list(collection.aggregate(pipeline))
            if rich_sample:
                sample_doc = rich_sample[0]['doc']
                tqdm.write(f"     Sample keys: {list(sample_doc.keys())}")
        except Exception:
            pass
    
    total_elapsed = time.time() - total_start
    print(f"\n✅ MongoDB loading complete in {total_elapsed:.1f}s")
    print("=" * 80 + "\n")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def ensure_mysql_database_exists(host: str, port: int, user: str, password: str, db_name: str) -> None:
    """Create the MySQL database if it doesn't exist, using a server-level connection.

    We connect without specifying a database first, run CREATE DATABASE IF NOT EXISTS,
    and then let the rest of the pipeline connect to the DB-specific engine.
    """
    server_engine = create_engine(
        f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/"
    )
    print("\n" + "=" * 80)
    print("🧱 ENSURING MYSQL DATABASE EXISTS")
    print("=" * 80)
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}`"))
        conn.commit()
        print(f"✓ Database ensured: {db_name}")
    server_engine.dispose()

def main() -> None:
    """Main execution pipeline"""
    import time
    pipeline_start = time.time()
    
    print("\n" + "=" * 80)
    print("🚀 DATABASE LOADING PIPELINE")
    print("=" * 80 + "\n")
    
    # 1. Load CSV data
    dataframes = load_all_csvs(FINAL_DIR)
    
    # 2. Ensure MySQL database exists, then connect
    print("=" * 80)
    print("🔌 CONNECTING TO MYSQL")
    print("=" * 80)
    # First, create the database if needed using a server-level connection
    ensure_mysql_database_exists(
        host=MYSQL_CONFIG['host'],
        port=MYSQL_CONFIG['port'],
        user=MYSQL_CONFIG['user'],
        password=MYSQL_CONFIG['password'],
        db_name=MYSQL_CONFIG['database'],
    )

    # Now connect to the specific database with optimized settings
    mysql_engine = create_engine(
        f"mysql+mysqlconnector://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}@"
        f"{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}",
        pool_size=10,  # Connection pooling
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections
        echo=False  # Disable SQL echo for performance
    )

    print(f"✓ Connected to MySQL DB '{MYSQL_CONFIG['database']}' at {MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}")
    print("=" * 80 + "\n")
    
    # 3. Execute schema
    execute_schema(SCHEMA_PATH, mysql_engine)

    # 3.1 Verify schema integrity (tables + foreign keys)
    try:
        verify_mysql_schema(mysql_engine, MYSQL_CONFIG['database'])
    except Exception as e:
        print("❌ Schema verification error:", e)
        print("   Aborting before data insert to avoid implicit table creation without constraints.")
        mysql_engine.dispose()
        return
    
    # 4. Load MySQL data
    load_mysql_data(dataframes, DATA_LOADING_CONFIG, mysql_engine)
    
    # 5. Connect to MongoDB
    print("=" * 80)
    print("🔌 CONNECTING TO MONGODB")
    print("=" * 80)
    
    if MONGODB_USE_SERVER_API:
        mongo_client = MongoClient(
            MONGODB_URI, 
            server_api=ServerApi('1'),
            maxPoolSize=50  # Increase connection pool
        )
    else:
        mongo_client = MongoClient(
            MONGODB_URI,
            maxPoolSize=50
        )
    
    mongo_db = mongo_client[MONGODB_DATABASE]
    
    # Fix: Handle potential None in URI split
    uri_display = MONGODB_URI.split('@')[1].split('/')[0] if '@' in MONGODB_URI else MONGODB_DATABASE
    print(f"✓ Connected to MongoDB: {uri_display}")
    print("=" * 80 + "\n")
    
    # 6. Load MongoDB data
    load_mongodb_data(dataframes, DATA_LOADING_CONFIG, mongo_db)
    
    # 7. Verification
    print("=" * 80)
    print("✅ VERIFICATION")
    print("=" * 80)
    
    mysql_total = 0
    with mysql_engine.connect() as conn:
        for table_name in DATA_LOADING_CONFIG['MySQL']['insert_order']:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            count = result.fetchone()
            # Fix: Handle potential None result
            if count:
                print(f"  MySQL {table_name}: {count[0]:,} rows")
                mysql_total += count[0]
    
    mongo_total = 0
    for collection_name in DATA_LOADING_CONFIG['MongoDB']['collections'].keys():
        count = mongo_db[collection_name].count_documents({})
        print(f"  MongoDB {collection_name}: {count:,} documents")
        mongo_total += count
    
    print("=" * 80 + "\n")
    
    # Cleanup
    mongo_client.close()
    mysql_engine.dispose()
    
    # Final summary
    total_elapsed = time.time() - pipeline_start
    total_records = mysql_total + mongo_total
    
    print("=" * 80)
    print("✅ DATABASE LOADING COMPLETE!")
    print("=" * 80)
    print(f"Total time: {total_elapsed:.1f}s")
    print(f"Total records: {total_records:,} ({total_records/total_elapsed:,.0f} records/s)")
    print(f"MySQL: {mysql_total:,} rows | MongoDB: {mongo_total:,} documents")
    print("=" * 80)


if __name__ == "__main__":
    main()