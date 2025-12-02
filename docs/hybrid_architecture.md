# Hybrid MySQL + MongoDB Design for Book Recommendation System

## Overview
This project implements a **hybrid database architecture** as required by the professor:
- **MySQL**: Structured, transactional, and reference data
- **MongoDB**: Semi-structured, flexible, user-driven data

Both databases **interoperate** via shared identifiers (user_id, isbn).

---

## MySQL Schema (Relational - Structured Data)

### Entities

#### 1. `users` table
Stores core user identity and demographics (structured, transactional).

| Column      | Type         | Constraints         | Description                     |
|-------------|--------------|---------------------|---------------------------------|
| user_id     | INT          | PRIMARY KEY         | Unique user identifier          |
| age         | INT          | NULL                | User age                        |
| location    | VARCHAR(255) | NULL                | User location                   |
| created_at  | DATETIME     | DEFAULT NOW()       | Account creation timestamp      |

**Indexes**: PRIMARY KEY on `user_id`

#### 2. `books` table
Stores core book metadata (structured, reference data).

| Column    | Type         | Constraints    | Description               |
|-----------|--------------|----------------|---------------------------|
| isbn      | VARCHAR(20)  | PRIMARY KEY    | Book ISBN (unique ID)     |
| title     | VARCHAR(512) | NULL           | Book title                |
| author    | VARCHAR(255) | NULL           | Primary author            |
| year      | INT          | NULL           | Publication year          |
| publisher | VARCHAR(255) | NULL           | Publisher name            |

**Indexes**:
- PRIMARY KEY on `isbn`
- INDEX on `author`
- INDEX on `title`

#### 3. `ratings` table
Transactional rating events (append-only log).

| Column     | Type     | Constraints                  | Description                |
|------------|----------|------------------------------|----------------------------|
| id         | INT      | PRIMARY KEY AUTO_INCREMENT   | Rating record ID           |
| user_id    | INT      | FOREIGN KEY → users.user_id  | User who rated             |
| isbn       | VARCHAR  | FOREIGN KEY → books.isbn     | Book that was rated        |
| rating     | FLOAT    | NOT NULL                     | Rating value (0-10)        |
| timestamp  | DATETIME | DEFAULT NOW()                | When rating was created    |

**Constraints**:
- FOREIGN KEY `user_id` → `users.user_id` ON DELETE CASCADE
- FOREIGN KEY `isbn` → `books.isbn` ON DELETE CASCADE
- UNIQUE constraint on (`user_id`, `isbn`)

**Indexes**:
- PRIMARY KEY on `id`
- INDEX on `user_id`
- INDEX on `isbn`
- INDEX on `rating`
- INDEX on `timestamp`
- UNIQUE INDEX on (`user_id`, `isbn`)

### ER Diagram (MySQL)

```
+-------------+        1:N         +-------------+        N:1        +--------------+
|   users     |------------------>  |   ratings   | <----------------|    books     |
+-------------+                     +-------------+                  +--------------+
| user_id (PK)|                     | id (PK)     |                  | isbn (PK)    |
| age         |                     | user_id (FK)|                  | title        |
| location    |                     | isbn (FK)   |                  | author       |
| created_at  |                     | rating      |                  | year         |
+-------------+                     | timestamp   |                  | publisher    |
                                    +-------------+                  +--------------+
```

---

## MongoDB Schema (Document - Semi-Structured Data)

### Collections

#### 1. `user_profiles` collection
Stores flexible user preferences, reading history, and behavioral data.

**Document structure**:
```json
{
  "_id": ObjectId("..."),
  "user_id": 12345,  // SHARED ID with MySQL
  "preferences": {
    "favorite_books": ["isbn1", "isbn2", ...],
    "avg_rating": 7.5,
    "total_ratings": 42,
    "favorite_genres": ["Fiction", "Mystery"],
    "preferred_authors": ["Author A", "Author B"]
  },
  "reading_history": [
    {"isbn": "...", "rating": 8, "read_date": "2024-01-15"},
    ...
  ],
  "tags": ["bookworm", "mystery-lover"],
  "updated_at": ISODate("2025-01-01T12:00:00Z")
}
```

**Indexes**:
- Unique index on `user_id`

#### 2. `book_details` collection
Stores extended book metadata, reviews, categories (nested, flexible).

**Document structure**:
```json
{
  "_id": ObjectId("..."),
  "isbn": "0345417953",  // SHARED ID with MySQL
  "extended_metadata": {
    "description": "Long text description...",
    "categories": ["Science Fiction", "Classic", "Adventure"],
    "avg_rating": 8.9,
    "num_ratings": 1234,
    "language": "en",
    "page_count": 215
  },
  "reviews": [
    {
      "user_id": 12345,
      "review_text": "Brilliant book!",
      "helpful_count": 42,
      "timestamp": ISODate("...")
    },
    ...
  ],
  "similar_books": ["isbn1", "isbn2"],
  "updated_at": ISODate("2025-01-01T12:00:00Z")
}
```

**Indexes**:
- Unique index on `isbn`
- Index on `extended_metadata.categories`

#### 3. `interaction_logs` collection
Event stream for user-item interactions (clicks, views, searches).

**Document structure**:
```json
{
  "_id": ObjectId("..."),
  "user_id": 12345,  // SHARED ID with MySQL
  "isbn": "0345417953",  // SHARED ID with MySQL
  "event_type": "view|click|search|rate|purchase",
  "timestamp": ISODate("2025-01-01T14:30:00Z"),
  "metadata": {
    "source": "homepage",
    "device": "mobile",
    "rating_value": 8
  }
}
```

**Indexes**:
- Compound index on (`user_id`, `timestamp` DESC)
- Index on `isbn`

#### 4. `recommendation_cache` collection
Pre-computed recommendations for fast retrieval.

**Document structure**:
```json
{
  "_id": ObjectId("..."),
  "user_id": 12345,  // SHARED ID with MySQL
  "recommendations": [
    {"isbn": "...", "score": 9.2, "reason": "collaborative_filtering"},
    {"isbn": "...", "score": 8.7, "reason": "content_based"},
    ...
  ],
  "generated_at": ISODate("2025-01-01T10:00:00Z"),
  "ttl": 86400  // cache TTL in seconds
}
```

**Indexes**:
- Unique index on `user_id`

---

## Integration Points (MySQL ↔ MongoDB)

### Shared Identifiers
- **`user_id`**: Links `users` (MySQL) ↔ `user_profiles` (MongoDB) ↔ `interaction_logs` (MongoDB)
- **`isbn`**: Links `books` (MySQL) ↔ `book_details` (MongoDB) ↔ `interaction_logs` (MongoDB)

### Data Flow Examples

#### 1. User Profile Query (Hybrid)
```
1. Fetch user demographics from MySQL: SELECT * FROM users WHERE user_id = ?
2. Enrich with preferences from MongoDB: db.user_profiles.find_one({"user_id": ?})
3. Return combined profile
```

#### 2. Book Detail Page (Hybrid)
```
1. Fetch core metadata from MySQL: SELECT * FROM books WHERE isbn = ?
2. Enrich with extended metadata from MongoDB: db.book_details.find_one({"isbn": ?})
3. Fetch recent interactions: db.interaction_logs.find({"isbn": ?}).sort({"timestamp": -1}).limit(10)
4. Return complete book view
```

#### 3. Recommendation Generation (Hybrid)
```
1. Load ratings from MySQL: SELECT user_id, isbn, rating FROM ratings
2. Train CF model (pandas DataFrame from MySQL)
3. Fetch user preferences from MongoDB: db.user_profiles.find_one({"user_id": ?})
4. Apply preference filters/boosts
5. Cache results in MongoDB: db.recommendation_cache.update_one(...)
```

---

## Normalization

### MySQL (3NF - Third Normal Form)
- **1NF**: All columns atomic, no repeating groups
- **2NF**: No partial dependencies (all non-key attributes depend on entire primary key)
- **3NF**: No transitive dependencies (non-key attributes depend only on primary key)

All three tables satisfy 3NF:
- `users`: demographics depend solely on `user_id`
- `books`: metadata depends solely on `isbn`
- `ratings`: rating/timestamp depend on composite (`user_id`, `isbn`)

### MongoDB (Denormalized by Design)
- Documents embed related data for fast reads
- Accepts duplication for query performance
- Flexible schema allows evolution without migrations

---

## Why This Split?

| Data Type                     | Database | Reason                                                    |
|-------------------------------|----------|-----------------------------------------------------------|
| User identity, demographics   | MySQL    | Structured, ACID transactions, relational queries         |
| Book core metadata            | MySQL    | Reference data, normalized, joins with ratings            |
| Rating transactions           | MySQL    | ACID guarantees, foreign keys, time-series analytics      |
| User preferences, history     | MongoDB  | Flexible schema, nested arrays, evolving user behavior    |
| Book reviews, categories      | MongoDB  | Variable-length nested data, no fixed schema              |
| Interaction event logs        | MongoDB  | High-volume writes, document-per-event, flexible metadata |
| Recommendation cache          | MongoDB  | Ephemeral data, TTL indexes, fast key-value lookups       |

This design leverages the **strengths of both systems** while maintaining clean integration via shared IDs.
