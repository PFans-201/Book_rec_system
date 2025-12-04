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
from typing import Dict, List
import warnings
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

# ----------------- Load environment -----------------
# Specify exact path to .env file
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    print(f"✓ Loaded environment from: {ENV_PATH}")
else:
    print(f"⚠️  .env file not found at: {ENV_PATH}")
    print(f"   Current working directory: {Path.cwd()}")

# Load credentials from environment
db_name = os.getenv("DB_NAME")
host = os.getenv("HOST")

mdb_port = os.getenv("MDB_PORT")
mdb_user = os.getenv("MDB_USER")
mdb_password = os.getenv("MDB_PASSWORD")
mdb_cluster = os.getenv("MDB_CLUSTER")  # e.g., "bookreccluster.xxxxx.mongodb.net"
mdb_appname = os.getenv("MDB_APPNAME")
mdb_use_atlas = os.getenv("MDB_USE_ATLAS", "false").lower() == "true"  # Flag for Atlas vs local


msql_user = os.getenv("MSQL_USER")
msql_password = os.getenv("MSQL_PASSWORD")
msql_port = os.getenv("MSQL_PORT", "3306")

# Validate credentials
if not all([msql_user, msql_password]):
    print("⚠️  MySQL credentials not found in environment!")
    print(f"   MSQL_USER: {msql_user}")
    print(f"   MSQL_PASSWORD: {'***' if msql_password else 'NOT SET'}")

if not all([mdb_user, mdb_password]):
    print("⚠️  MongoDB credentials not found in environment!")
    print(f"   MDB_USER: {mdb_user}")
    print(f"   MDB_PASSWORD: {'***' if mdb_password else 'NOT SET'}")

if mdb_use_atlas and not all([mdb_cluster, mdb_appname]):
    print("⚠️  MDB_USE_ATLAS is true but MDB_CLUSTER or MDB_APPNAME not set!")

# Database connections - USE ENVIRONMENT VARIABLES
MYSQL_CONFIG = {
    'host': host,
    'user': msql_user,
    'password': msql_password,
    'database': db_name,
    'port': int(msql_port) if msql_port else 3306,
}

# MongoDB Configuration (Atlas or Local)
if mdb_use_atlas:
    # MongoDB Atlas connection
    MONGODB_URI = f"mongodb+srv://{mdb_user}:{mdb_password}@{mdb_cluster}/?retryWrites=true&w=majority&appName=Cluster0"
    MONGODB_USE_SERVER_API = True
    print(f"✓ Using MongoDB Atlas: {mdb_cluster}")
else:
    # Local MongoDB connection
    MONGODB_URI = f"mongodb://{mdb_user}:{mdb_password}@{host or 'localhost'}:{int(mdb_port) if mdb_port else 27017}/"
    MONGODB_USE_SERVER_API = False
    print(f"✓ Using Local MongoDB: {host or 'localhost'}:{int(mdb_port) if mdb_port else 27017}")

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
        dataframes[f.stem] = df
        print(f"✓ Loaded {f.stem}: {len(df):,} rows, {len(df.columns)} columns")
    
    print("=" * 80 + "\n")
    return dataframes


# ============================================================================
# MYSQL LOADING
# ============================================================================

def execute_schema(schema_path: Path, connection):
    """Execute MySQL schema DDL file"""
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
            # Change delimiter
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
    
    # Execute statements
    cursor = connection.cursor()
    for i, stmt in enumerate(statements):
        stmt = stmt.strip().rstrip(';').rstrip('$$')
        if stmt:
            try:
                cursor.execute(stmt)
                print(f"✓ Executed statement {i+1}/{len(statements)}")
            except Exception as e:
                print(f"⚠️  Statement {i+1} failed: {e}")
                print(f"   SQL: {stmt[:100]}...")
    
    connection.commit()
    print("=" * 80 + "\n")


def clean_dataframe_for_mysql(df: pd.DataFrame, columns: List[str], 
                               rename_map: Dict[str, str] = None) -> pd.DataFrame:
    """Prepare dataframe for MySQL insertion"""
    df_clean = df[columns].copy()
    
    if rename_map:
        df_clean = df_clean.rename(columns=rename_map)
    
    # Replace NaN with None for SQL NULL
    df_clean = df_clean.where(pd.notna(df_clean), None)
    
    # Convert numpy types to Python native types
    for col in df_clean.columns:
        if df_clean[col].dtype == np.int64:
            df_clean[col] = df_clean[col].astype('Int64')
        elif df_clean[col].dtype == np.float64:
            df_clean[col] = df_clean[col].astype(float)
        elif df_clean[col].dtype == bool:
            df_clean[col] = df_clean[col].astype(int)
    
    return df_clean


def load_mysql_data(dataframes: Dict[str, pd.DataFrame], config: Dict, mysql_engine):
    """Load data into MySQL following insertion order"""
    print("=" * 80)
    print("📊 LOADING DATA INTO MYSQL")
    print("=" * 80)
    
    mysql_config = config['MySQL']
    insert_order = mysql_config['insert_order']
    tables_config = mysql_config['tables']
    
    for table_name in insert_order:
        table_config = tables_config[table_name]
        df_name = table_config['df_name']
        columns = table_config['columns']
        rename_map = table_config.get('rename', {})
        
        if df_name not in dataframes:
            print(f"⚠️  Skipping {table_name}: DataFrame '{df_name}' not found")
            continue
        
        print(f"\n📋 Inserting into: {table_name}")
        
        df_to_insert = clean_dataframe_for_mysql(
            dataframes[df_name], 
            columns, 
            rename_map
        )
        
        # Exclude AUTO_INCREMENT columns
        if table_name == 'ratings':
            insert_columns = [col for col in df_to_insert.columns if col != 'ratings_seq']
            df_to_insert = df_to_insert[insert_columns]
        
        print(f"  Rows to insert: {len(df_to_insert):,}")
        print(f"  Columns: {list(df_to_insert.columns)}")
        
        try:
            df_to_insert.to_sql(
                name=table_name,
                con=mysql_engine,
                if_exists='append',
                index=False,
                chunksize=1000,
                method='multi'
            )
            print(f"  ✅ Successfully inserted {len(df_to_insert):,} rows")
        except Exception as e:
            print(f"  ❌ Error inserting into {table_name}: {e}")
            print(f"  Sample data:\n{df_to_insert.head(3)}")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# MONGODB LOADING
# ============================================================================

def build_mongo_document(row: pd.Series, config: Dict) -> Dict:
    """Build a MongoDB document from a DataFrame row"""
    doc = {}
    
    for category, fields in config.items():
        category_data = {}
        for field in fields:
            if field in row.index and pd.notna(row[field]):
                value = row[field]
                
                # Convert numpy types to Python native types
                if isinstance(value, (np.integer, np.int64)):
                    value = int(value)
                elif isinstance(value, (np.floating, np.float64)):
                    value = float(value)
                elif isinstance(value, np.bool_):
                    value = bool(value)
                elif pd.isna(value):
                    continue
                
                category_data[field] = value
        
        if category_data:
            doc[category] = category_data
    
    return doc


def load_mongodb_data(dataframes: Dict[str, pd.DataFrame], config: Dict, mongo_db):
    """Load data into MongoDB collections"""
    print("=" * 80)
    print("📊 LOADING DATA INTO MONGODB")
    print("=" * 80)
    
    mongodb_config = config['MongoDB']
    collections_config = mongodb_config['collections']
    
    for collection_name, coll_config in collections_config.items():
        df_name = coll_config['df_name']
        id_field = coll_config['id_field']
        fields_config = coll_config['fields']
        
        if df_name not in dataframes:
            print(f"⚠️  Skipping {collection_name}: DataFrame '{df_name}' not found")
            continue
        
        print(f"\n📋 Inserting into collection: {collection_name}")
        
        df = dataframes[df_name]
        collection = mongo_db[collection_name]
        
        # Drop collection if exists (for clean repeated runs)
        if collection_name in mongo_db.list_collection_names():
            collection.drop()
            print(f"  ⚠️  Dropped existing collection: {collection_name}")
        
        # Build documents
        documents = []
        for _, row in df.iterrows():
            doc = build_mongo_document(row, fields_config)
            
            if doc:
                doc['_id'] = row[id_field]
                documents.append(doc)
            
            # Batch insert every 1000 documents
            if len(documents) >= 1000:
                collection.insert_many(documents, ordered=False)
                documents = []
        
        # Insert remaining documents
        if documents:
            collection.insert_many(documents, ordered=False)
        
        doc_count = collection.count_documents({})
        print(f"  ✅ Successfully inserted {doc_count:,} documents")
        
        # Show sample document
        sample = collection.find_one()
        print("  Sample document structure:")
        if sample:
            print(f"    {list(sample.keys())}")
    
    print("\n" + "=" * 80 + "\n")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution pipeline"""
    print("\n" + "=" * 80)
    print("🚀 DATABASE LOADING PIPELINE")
    print("=" * 80 + "\n")
    
    # 1. Load CSV data
    dataframes = load_all_csvs(FINAL_DIR)
    
    # 2. Connect to MySQL
    print("=" * 80)
    print("🔌 CONNECTING TO MYSQL")
    print("=" * 80)
    
    mysql_engine = create_engine(
        f"mysql+mysqlconnector://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}@"
        f"{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}"
    )
    
    print(f"✓ Connected to MySQL: {MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}")
    print("=" * 80 + "\n")
    
    # 3. Execute schema
    execute_schema(SCHEMA_PATH, mysql_engine)
    
    # 4. Load MySQL data
    load_mysql_data(dataframes, DATA_LOADING_CONFIG, mysql_engine)
    
    # 5. Connect to MongoDB
    print("=" * 80)
    print("🔌 CONNECTING TO MONGODB")
    print("=" * 80)
    
    if MONGODB_USE_SERVER_API:
        mongo_client = MongoClient(MONGODB_URI, server_api=ServerApi('1'))
    else:
        mongo_client = MongoClient(MONGODB_URI)
    
    mongo_db = mongo_client[MONGODB_DATABASE]
    
    print(f"✓ Connected to MongoDB: {MONGODB_URI.split('@')[1].split('/')[0]}")
    print("=" * 80 + "\n")
    
    # 6. Load MongoDB data
    load_mongodb_data(dataframes, DATA_LOADING_CONFIG, mongo_db)
    
    # 7. Verification
    print("=" * 80)
    print("✅ VERIFICATION")
    print("=" * 80)
    
    with mysql_engine.connect() as conn:
        for table_name in DATA_LOADING_CONFIG['MySQL']['insert_order']:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            count = result.fetchone()[0]
            print(f"  MySQL {table_name}: {count:,} rows")
    
    for collection_name in DATA_LOADING_CONFIG['MongoDB']['collections'].keys():
        count = mongo_db[collection_name].count_documents({})
        print(f"  MongoDB {collection_name}: {count:,} documents")
    
    print("=" * 80 + "\n")
    
    # Cleanup
    mongo_client.close()
    
    print("=" * 80)
    print("✅ DATABASE LOADING COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    main()