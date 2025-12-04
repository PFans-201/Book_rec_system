# Database Documentation

This folder contains all database schemas, documentation, and loading scripts for the Book Recommendation System.

## 📁 Folder Structure

```
db/
├── README.md                      # This file
├── mysql_schema.sql               # MySQL DDL schema
├── mongodb_schema.md              # MongoDB schema documentation
├── hybrid_architecture.md         # Integration patterns & connection guide
├── mysql_er_diagram.md            # MySQL ER diagram (Mermaid)
└── load_data.py                   # Data loading pipeline (in scripts/)
```

## 🗄️ Database Architecture

This project uses a **hybrid polyglot persistence** architecture:

- **MySQL**: Relational data with ACID guarantees (users, books, ratings, genres)
- **MongoDB**: Document-based flexible metadata and computed metrics

### Why Hybrid?

| Requirement | Database | Reason |
|-------------|----------|--------|
| User-book ratings | MySQL | Transactional integrity, FK constraints |
| Genre hierarchies | MySQL | Normalized relations, JOIN queries |
| Book descriptions/images | MongoDB | Sparse fields, flexible schema |
| Computed metrics | MongoDB | Denormalized, read-optimized aggregates |
| User preferences | MongoDB | Variable-length arrays, nested documents |

📖 **Read more**: [hybrid_architecture.md](hybrid_architecture.md)

---

## 🏗️ MySQL Schema

### Tables Overview

```
root_genres (3 root categories)
    ↓
subgenres (50+ specific genres)
    ↓
books (270K+ books)  ←→  users (278K+ users)
    ↓                      ↓
book_root_genres      ratings (1M+ ratings)
book_subgenres
```

### Key Tables

- **users**: Demographics, location, activity flags
- **books**: Core metadata (title, authors, publisher, year)
- **ratings**: User-book interactions with sequence tracking
- **root_genres** / **subgenres**: Genre taxonomy
- **book_root_genres** / **book_subgenres**: Many-to-many relationships

### Features

✅ Foreign key constraints ensure referential integrity  
✅ AUTO_INCREMENT triggers for rating sequences  
✅ Cascading deletes for data consistency  
✅ CHECK constraints for data validation  

📖 **Full schema**: [mysql_schema.sql](mysql_schema.sql)  
📊 **ER Diagram**: [er_diagram.md](er_diagram.md)

---

## 📄 MongoDB Schema

### Collections Overview

```
books_metadata (270K+ documents)
    ↓
  - extra_metadata (images, descriptions, price)
  - rating_metrics (avg, std, count, category)
  - popularity_metrics (recent_count, popularity score)

users_profiles (278K+ documents)
    ↓
  - profile (reader_level, critic_profile, stats)
  - preferences (genres, authors, price range)
```

### Key Features

✅ Flexible schema handles sparse data  
✅ Array fields for multi-valued attributes  
✅ Nested documents for logical grouping  
✅ Pre-computed metrics for fast queries  

📖 **Full schema**: [mongodb_schema.md](mongodb_schema.md)

---

## 🔌 Database Connection

### Prerequisites

1. **MySQL Server** (8.0+)
2. **MongoDB Server** (5.0+) or **MongoDB Atlas**
3. Python packages:
   ```bash
   pip install pandas sqlalchemy pymongo mysql-connector-python python-dotenv
   ```

### Environment Configuration

Create a `.env` file in the project root:

```env
# MySQL Configuration
MSQL_USER=your_mysql_user
MSQL_PASSWORD=your_mysql_password
MSQL_PORT=3306
HOST=localhost

# MongoDB Configuration (Local)
MDB_USER=your_mongo_user
MDB_PASSWORD=your_mongo_password
MDB_PORT=27017
MDB_USE_ATLAS=false

# MongoDB Configuration (Atlas)
# MDB_USE_ATLAS=true
# MDB_CLUSTER=yourcluster.xxxxx.mongodb.net
# MDB_APPNAME=Cluster0

# Database Name
DB_NAME=bookrec
```

### Connection URLs

**MySQL:**
```python
mysql+mysqlconnector://user:password@localhost:3306/bookrec
```

**MongoDB Local:**
```python
mongodb://user:password@localhost:27017/
```

**MongoDB Atlas:**
```python
mongodb+srv://user:password@cluster.mongodb.net/?retryWrites=true&w=majority
```

---

## 🚀 Loading Data

### Pipeline Overview

The `load_data.py` script handles the complete ETL process:

```
CSV Files → Validate → MySQL (structured) → MongoDB (metadata)
```

### Execution Steps

1. **Prepare CSV files** in `data/final/`:
   - `users.csv`
   - `books.csv`
   - `ratings.csv`
   - `root_genres.csv`
   - `subgenres.csv`
   - `book_root_genres.csv`
   - `book_subgenres.csv`

2. **Configure environment** (`.env` file)

3. **Run the pipeline**:
   ```bash
   python scripts/load_data.py
   ```

### What the Script Does

1. ✅ Loads all CSV files into memory
2. ✅ Connects to MySQL and creates database if needed
3. ✅ Executes DDL schema (`mysql_schema.sql`)
4. ✅ Verifies schema integrity (tables + foreign keys)
5. ✅ Loads MySQL data in FK-safe order
6. ✅ Connects to MongoDB (local or Atlas)
7. ✅ Loads MongoDB collections with denormalized data
8. ✅ Verifies row/document counts

### Expected Output

```
================================
🚀 DATABASE LOADING PIPELINE
================================

✓ Loaded environment from: /path/to/.env
✓ Using Local MongoDB: localhost:27017

📂 LOADING CSV FILES
✓ Loaded users: 278,858 rows, 20 columns
✓ Loaded books: 271,360 rows, 25 columns
✓ Loaded ratings: 1,149,780 rows, 7 columns
...

📊 LOADING DATA INTO MYSQL
✓ Successfully inserted 278,858 rows into users
✓ Successfully inserted 271,360 rows into books
✓ Successfully inserted 1,149,780 rows into ratings
...

📊 LOADING DATA INTO MONGODB
✓ Successfully inserted 271,360 documents into books_metadata
✓ Successfully inserted 105,283 documents into users_profiles
...

✅ VERIFICATION
MySQL users: 278,858 rows
MySQL books: 271,360 rows
MySQL ratings: 1,149,780 rows
MongoDB books_metadata: 271,360 documents
MongoDB users_profiles: 105,283 documents

✅ DATABASE LOADING COMPLETE!
```

---

## 🔍 Querying Examples

### MySQL Queries

**Find all ratings by a user:**
```sql
SELECT b.title, r.rating, r.r_seq_user
FROM ratings r
JOIN books b ON r.isbn = b.isbn
WHERE r.user_id = 12345
ORDER BY r.r_seq_user DESC;
```

**Books by genre:**
```sql
SELECT b.isbn, b.title, rg.root_name
FROM books b
JOIN book_root_genres brg ON b.isbn = brg.isbn
JOIN root_genres rg ON brg.root_id = rg.root_id
WHERE rg.root_name = 'Fiction';
```

### MongoDB Queries

**Highly-rated fiction books under $20:**
```javascript
db.books_metadata.find({
  "extra_metadata.root_genres": "Fiction",
  "extra_metadata.price_usd": { $lte: 20 },
  "rating_metrics.r_avg": { $gte: 8.0 },
  "rating_metrics.r_count": { $gte: 50 }
}).sort({ "rating_metrics.r_avg": -1 }).limit(10)
```

**Active users who prefer sci-fi:**
```javascript
db.users_profiles.find({
  "profile.reader_level": "active",
  "preferences.pref_root_genres": "Science Fiction",
  "profile.has_preferences": true
})
```

### Hybrid Query (Application Layer)

**Recommend books for user:**
```python
# 1. Get user preferences (MongoDB)
user_profile = mongo_db.users_profiles.find_one({"_id": user_id})
pref_genres = user_profile["preferences"]["pref_root_genres"]

# 2. Find candidate books (MongoDB)
candidates = mongo_db.books_metadata.find({
    "extra_metadata.root_genres": {"$in": pref_genres},
    "rating_metrics.r_avg": {"$gte": 7.0}
}).limit(50)

candidate_isbns = [doc["_id"] for doc in candidates]

# 3. Filter out already rated (MySQL)
query = "SELECT isbn FROM ratings WHERE user_id = %s AND isbn IN %s"
rated_isbns = mysql_cursor.execute(query, (user_id, tuple(candidate_isbns)))

# 4. Return recommendations
recommendations = [isbn for isbn in candidate_isbns if isbn not in rated_isbns]
```

---

## 📊 Schema Diagrams

### MySQL ER Diagram

See [er_diagram.md](er_diagram.md) for the full entity-relationship diagram.

**Key Relationships:**
- `users` 1:N `ratings` N:1 `books`
- `books` N:M `root_genres` (via `book_root_genres`)
- `books` N:M `subgenres` (via `book_subgenres`)
- `root_genres` 1:N `subgenres`

### MongoDB Document Structure

```
books_metadata/
  └─ {_id: isbn}
      ├─ extra_metadata{} (11 fields)
      ├─ rating_metrics{} (6 fields)
      └─ popularity_metrics{} (3 fields)

users_profiles/
  └─ {_id: user_id}
      ├─ profile{} (10 fields)
      └─ preferences{} (8 fields)
```

---

## 🛠️ Maintenance

### Updating Computed Metrics

After bulk rating updates, recompute MongoDB metrics:

```python
from scripts.compute_metrics import recompute_all_metrics
recompute_all_metrics(mysql_engine, mongo_db)
```

### Adding Indexes

**MySQL:**
```sql
CREATE INDEX idx_ratings_user ON ratings(user_id);
CREATE INDEX idx_books_year ON books(publication_year);
```

**MongoDB:**
```javascript
db.books_metadata.createIndex({"rating_metrics.r_avg": -1})
db.users_profiles.createIndex({"profile.reader_level": 1})
```

### Backup Strategy

**MySQL:**
```bash
mysqldump -u user -p bookrec > backup_mysql.sql
```

**MongoDB:**
```bash
mongodump --uri="mongodb://user:password@localhost:27017/bookrec" --out=backup_mongo/
```

---

## 🐛 Troubleshooting

| Issue | Likely Cause | Solution |
|-------|--------------|----------|
| `MySQL: FK constraint fails` | Loading order wrong | Check `insert_order` in config |
| `MongoDB: Duplicate key error` | Collection already exists | Drop collection or use `if_exists='append'` |
| `Cannot connect to MySQL` | Wrong credentials/host | Verify `.env` file, check MySQL service |
| `Cannot connect to MongoDB Atlas` | Wrong cluster URL | Check `MDB_CLUSTER` in `.env` |
| `Missing data in MongoDB` | ETL failed silently | Check logs, verify CSV columns match config |
| `Schema verification failed` | Schema not executed | Ensure `mysql_schema.sql` ran successfully |

### Debug Mode

Add verbose logging to `load_data.py`:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 📚 Additional Resources

- **MySQL Documentation**: https://dev.mysql.com/doc/
- **MongoDB Documentation**: https://docs.mongodb.com/
- **SQLAlchemy**: https://docs.sqlalchemy.org/
- **PyMongo**: https://pymongo.readthedocs.io/

---

## 🤝 Contributing

When modifying the schema:

1. Update `mysql_schema.sql` or document MongoDB changes
2. Update this README and relevant documentation
3. Test the full pipeline with sample data
4. Update ER diagrams if relationships change
5. Document breaking changes in migration notes

---

## 📝 Notes

- **Knowledge cutoff**: Schema designed as of December 2024
- **Data size**: ~270K books, ~280K users, ~1.15M ratings
- **Update frequency**: Batch updates recommended for metrics
- **Consistency**: MySQL = strong, MongoDB = eventual
- **Primary keys**: `isbn` (books), `user_id` (users), composite (ratings)

---

**Last Updated**: December 2024  
**Version**: 1.0.0  
**Database**: bookrec (MySQL + MongoDB)