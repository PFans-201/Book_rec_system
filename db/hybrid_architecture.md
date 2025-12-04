# Hybrid Database Architecture

## Overview

This document describes how MySQL and MongoDB work together in the Book Recommendation System, their respective roles, and the integration patterns used.

---

## Architecture Pattern: Polyglot Persistence

The system uses **polyglot persistence** - leveraging multiple database technologies optimized for different data patterns:

- **MySQL**: ACID-compliant relational data with strong consistency
- **MongoDB**: Flexible document storage for sparse/nested data

### Design Philosophy

```
┌─────────────────────────────────────────────────────────────┐
│                   Application Layer                         │
│                (Recommendation Engine)                      │
└────────────┬────────────────────────────┬───────────────────┘
             │                            │
             ▼                            ▼
    ┌────────────────┐            ┌─────────────────┐
    │     MySQL      │            │    MongoDB      │
    │   (Structured) │            │  (Denormalized) │
    └────────────────┘            └─────────────────┘
         │                              │
         │  Core Data                   │  Extended Metadata
         │  + Relations                 │  + Computed Metrics
         └──────────────────────────────┘
              Connected via shared keys
                  (ISBN, user_id)
```

---

## Data Distribution Strategy

### MySQL Stores:

✅ **Core Entity Data** (normalized)
- Users: Demographics, location, identity
- Books: Title, authors, publisher, year
- Ratings: User-book interactions

✅ **Relational Structures**
- Genre hierarchies (root_genres → subgenres)
- Many-to-many relationships (book_root_genres, book_subgenres)
- Foreign key constraints

✅ **Transactional Data**
- Rating sequences (per-user, per-book)
- Referential integrity via FKs

### MongoDB Stores:

✅ **Extended Metadata** (denormalized)
- Book images, descriptions, preview links
- Sparse fields (price_usd - not all books have prices)
- Variable-length arrays (genres, tags)

✅ **Computed Metrics** (read-optimized)
- Rating aggregations (avg, std, count)
- Popularity scores
- User profiles (reading behavior)
- User preferences (genre, author preferences)

✅ **Flexible Schemas**
- Not all users have preferences
- Not all books have descriptions/images
- Array-based multi-value fields

---

## Connection Mechanism

### Shared Key Pattern

Both databases use **common identifiers** to link related data:

```
MySQL: books(isbn)           ←→  MongoDB: books_metadata(_id: isbn)
MySQL: users(user_id)        ←→  MongoDB: users_profiles(_id: user_id)
MySQL: ratings(user_id, isbn) ←→  Combined queries
```

### Connection Flow

```python
# 1. Query MySQL for structured data
mysql_engine = create_engine("mysql+mysqlconnector://...")
books_query = "SELECT isbn, title, authors FROM books WHERE isbn IN (...)"
books_df = pd.read_sql(books_query, mysql_engine)

# 2. Query MongoDB for metadata using same ISBNs
mongo_client = MongoClient("mongodb://...")
mongo_db = mongo_client["bookrec"]
isbns = books_df['isbn'].tolist()
metadata = mongo_db.books_metadata.find({"_id": {"$in": isbns}})

# 3. Join results in application layer
for book in books_df:
    book_meta = mongo_db.books_metadata.find_one({"_id": book['isbn']})
    # Combine structured + metadata
```

### No Direct Database-to-Database Connection

⚠️ **Important**: MySQL and MongoDB do **NOT** directly communicate with each other. Integration happens at the **application layer**:

1. Application queries MySQL for relational data
2. Application extracts keys (ISBN, user_id)
3. Application queries MongoDB using those keys
4. Application combines/joins results in memory

---

## Data Flow Patterns

### Pattern 1: Book Recommendation Query

```
User Request: "Recommend sci-fi books under $20"
                    ↓
        ┌───────────────────────┐
        │   Application Layer   │
        └───────────────────────┘
                ↓           ↓
         [MySQL]         [MongoDB]
    ┌─────────────┐   ┌──────────────────┐
    │ SELECT isbn │   │ db.books_metadata│
    │ FROM        │   │ .find({          │
    │ book_root_  │   │   "extra_metadata│
    │ genres      │   │   .root_genres": │
    │ WHERE root_id│   │   "Sci-Fi",     │
    │ = (Sci-Fi)  │   │   "extra_metadata│
    │             │   │   .price_usd":   │
    │             │   │   {$lte: 20}     │
    │             │   │ })               │
    └─────────────┘   └──────────────────┘
                ↓           ↓
        ┌──────────────────────────┐
        │   Join on ISBN in App    │
        │   Return: Books with     │
        │   metadata + structure   │
        └──────────────────────────┘
```

### Pattern 2: User Profile Enrichment

```
Query: "Get user 12345's profile and ratings"
                    ↓
         ┌─────────────┐         ┌──────────────┐
         │   MySQL     │         │   MongoDB    │
         ├─────────────┤         ├──────────────┤
         │ SELECT *    │         │ db.users_    │
         │ FROM users  │         │ profiles     │
         │ WHERE       │         │ .findOne({   │
         │ user_id=    │         │   _id: 12345 │
         │ 12345       │         │ })           │
         │             │         │              │
         │ SELECT *    │         │              │
         │ FROM ratings│         │              │
         │ WHERE       │         │              │
         │ user_id=    │         │              │
         │ 12345       │         │              │
         └─────────────┘         └──────────────┘
                    ↓
            Combined Result:
            {
              demographics: {...},  // MySQL
              ratings: [...],       // MySQL
              profile: {...},       // MongoDB
              preferences: {...}    // MongoDB
            }
```

### Pattern 3: Write Operations

```
New Rating Submitted
        ↓
┌───────────────────┐
│  Application      │
└───────────────────┘
        ↓
    [Transaction]
        ├──→ MySQL: INSERT INTO ratings (user_id, isbn, rating)
        │    • Triggers update r_seq_user, r_seq_book
        │    • FK checks ensure user/book exist
        │
        └──→ MongoDB: UPDATE books_metadata
             • Recompute rating_metrics
             • Update popularity_metrics
             
    [Post-process]
        └──→ MongoDB: UPDATE users_profiles
             • Recompute user profile stats
             • Update preferences if needed
```

---

## Synchronization Strategy

### During Initial Load (ETL Pipeline)

1. **MySQL First** (referential integrity)
   ```python
   # Load in FK-safe order
   load_order = ['root_genres', 'subgenres', 'users', 'books', 
                 'book_root_genres', 'book_subgenres', 'ratings']
   ```

2. **MongoDB Second** (denormalized data)
   ```python
   # Use same DataFrames, extract different columns
   for isbn in books_df['isbn']:
       mongo_doc = build_document(books_df, isbn)
       mongo_db.books_metadata.insert_one(mongo_doc)
   ```

### During Runtime Updates

| Event | MySQL Update | MongoDB Update | Sync Method |
|-------|--------------|----------------|-------------|
| New Rating | INSERT ratings | Update rating_metrics, user profile | Async job / Event |
| New Book | INSERT books, genres | INSERT books_metadata | Transactional |
| User Update | UPDATE users | UPDATE users_profiles (if needed) | On-demand |
| Batch Analytics | No change | Recompute all metrics | Scheduled job |

---

## Query Optimization Strategies

### 1. Read Splitting
- **Structured queries** → MySQL (JOINs, filtering on FKs)
- **Metadata queries** → MongoDB (flexible fields, arrays)

### 2. Denormalization Trade-offs
- **MongoDB duplicates** genre names from MySQL for read speed
- Accepts eventual consistency for computed metrics

### 3. Caching Layer
```
Application
    ↓
[Redis Cache] ← Store joined results
    ↓
MySQL + MongoDB
```

### 4. Aggregation Pipeline
```javascript
// Complex recommendation query entirely in MongoDB
db.books_metadata.aggregate([
  { $match: { "extra_metadata.root_genres": "Fiction" } },
  { $lookup: { /* Join ratings if needed */ } },
  { $sort: { "rating_metrics.r_avg": -1 } },
  { $limit: 20 }
])
```

---

## Benefits of This Architecture

✅ **Separation of Concerns**
- MySQL: Transaction integrity, relations
- MongoDB: Flexible metadata, fast reads

✅ **Scalability**
- MySQL: Vertical scaling for writes
- MongoDB: Horizontal scaling for reads

✅ **Performance**
- No complex JOINs for recommendation queries
- Pre-computed metrics in MongoDB
- Sparse data handled efficiently

✅ **Flexibility**
- Easy to add new metadata fields (MongoDB)
- Strict schema for core data (MySQL)

---

## Consistency Model

### Strong Consistency (MySQL)
- Ratings, user data, book catalog
- ACID transactions guaranteed

### Eventual Consistency (MongoDB)
- Computed metrics lag behind actual ratings
- Acceptable for recommendation use case
- Batch updates can sync periodically

---

## Integration Code Pattern

```python
class HybridRepository:
    def __init__(self, mysql_engine, mongo_db):
        self.mysql = mysql_engine
        self.mongo = mongo_db
    
    def get_book_full(self, isbn: str):
        # MySQL: Core data
        query = text("SELECT * FROM books WHERE isbn = :isbn")
        book_core = self.mysql.execute(query, {"isbn": isbn}).fetchone()
        
        # MongoDB: Metadata
        book_meta = self.mongo.books_metadata.find_one({"_id": isbn})
        
        # Combine
        return {
            **dict(book_core),
            "metadata": book_meta.get("extra_metadata", {}),
            "metrics": book_meta.get("rating_metrics", {})
        }
    
    def recommend_books(self, user_id: int, limit: int = 10):
        # Get user preferences from MongoDB
        user_profile = self.mongo.users_profiles.find_one({"_id": user_id})
        pref_genres = user_profile.get("preferences", {}).get("pref_root_genres", [])
        
        # Find candidate books in MongoDB
        candidates = self.mongo.books_metadata.find({
            "extra_metadata.root_genres": {"$in": pref_genres},
            "rating_metrics.r_avg": {"$gte": 7.0}
        }).sort("popularity_metrics.popularity", -1).limit(limit * 2)
        
        candidate_isbns = [doc["_id"] for doc in candidates]
        
        # Filter out already rated (MySQL)
        query = text("""
            SELECT isbn FROM ratings 
            WHERE user_id = :user_id AND isbn IN :isbns
        """)
        rated = self.mysql.execute(query, {
            "user_id": user_id, 
            "isbns": tuple(candidate_isbns)
        }).fetchall()
        rated_isbns = {r[0] for r in rated}
        
        # Return unrated candidates
        return [isbn for isbn in candidate_isbns 
                if isbn not in rated_isbns][:limit]
```

---

## Best Practices

1. **Always validate FKs in MySQL before MongoDB writes**
2. **Use transactions for MySQL, atomic updates for MongoDB**
3. **Cache frequently-accessed combined results**
4. **Document which database is source of truth for each field**
5. **Monitor sync lag between MySQL writes and MongoDB updates**
6. **Use indexes in both databases for shared key lookups**

---

## Troubleshooting

| Issue | Check | Solution |
|-------|-------|----------|
| Missing MongoDB docs | MySQL has records but Mongo empty | Re-run ETL load_mongodb_data() |
| FK violations | MySQL constraint errors | Load in correct order (root_genres first) |
| Stale metrics | MongoDB metrics don't match ratings | Run recompute job |
| Slow joins | Application combining large datasets | Add Redis cache layer |
| Data mismatch | ISBN in Mongo but not MySQL | Validate keys before insert |
