# MySQL Entity-Relationship Diagram

## Book Recommendation System - Database Schema

This ER diagram shows the relational structure of the MySQL database, including all tables, their attributes, and relationships.

---

## Diagram

```mermaid
erDiagram
    users ||--o{ ratings : "submits"
    books ||--o{ ratings : "receives"
    books ||--o{ book_root_genres : "has"
    books ||--o{ book_subgenres : "has"
    root_genres ||--o{ book_root_genres : "categorizes"
    root_genres ||--o{ subgenres : "contains"
    subgenres ||--o{ book_subgenres : "categorizes"

    users {
        INT user_id PK "AUTO_INCREMENT"
        TINYINT age "NOT NULL"
        VARCHAR age_group "NOT NULL"
        VARCHAR gender "NOT NULL"
        VARCHAR location "NULL"
        CHAR country "NOT NULL"
        DECIMAL loc_latitude "NULL, (9,6)"
        DECIMAL loc_longitude "NULL, (9,6)"
        BOOLEAN has_ratings "DEFAULT FALSE"
        BOOLEAN has_preferences "NOT NULL"
    }

    books {
        VARCHAR isbn PK "(10)"
        VARCHAR title "NOT NULL, (500)"
        TEXT authors "NOT NULL"
        SMALLINT publication_year "UNSIGNED, NOT NULL"
        VARCHAR publisher "NOT NULL, (150)"
        VARCHAR genre "NULL, (100)"
    }

    ratings {
        INT user_id PK_FK "FK to users"
        VARCHAR isbn PK_FK "FK to books, (10)"
        TINYINT rating "NOT NULL, 0-10"
        INT ratings_seq "UNIQUE, AUTO_INCREMENT"
        INT r_seq_user "NOT NULL"
        INT r_seq_book "NOT NULL"
        VARCHAR r_cat "NOT NULL, (50)"
    }

    root_genres {
        INT root_id PK "AUTO_INCREMENT"
        VARCHAR root_name "UNIQUE, NOT NULL, (100)"
    }

    subgenres {
        INT subgenre_id PK "AUTO_INCREMENT"
        VARCHAR subgenre_name "UNIQUE, NOT NULL, (100)"
        INT root_id FK "FK to root_genres, NULL"
    }

    book_root_genres {
        VARCHAR isbn PK_FK "FK to books, (10)"
        INT root_id PK_FK "FK to root_genres"
    }

    book_subgenres {
        VARCHAR isbn PK_FK "FK to books, (10)"
        INT subgenre_id PK_FK "FK to subgenres"
    }
```

---

## Relationship Descriptions

### Core Entities

#### users ↔ ratings (One-to-Many)
- **Relationship**: One user can submit many ratings
- **Cardinality**: 1:N
- **Foreign Key**: `ratings.user_id` → `users.user_id`
- **Cascade**: ON DELETE CASCADE (removes all ratings if user deleted)

#### books ↔ ratings (One-to-Many)
- **Relationship**: One book can receive many ratings
- **Cardinality**: 1:N
- **Foreign Key**: `ratings.isbn` → `books.isbn`
- **Cascade**: ON DELETE CASCADE (removes all ratings if book deleted)

### Genre Hierarchy

#### root_genres ↔ subgenres (One-to-Many)
- **Relationship**: One root genre contains many subgenres
- **Cardinality**: 1:N
- **Foreign Key**: `subgenres.root_id` → `root_genres.root_id`
- **Cascade**: ON DELETE SET NULL (preserves subgenres if root deleted)
- **Example**: "Fiction" → ["Mystery", "Romance", "Sci-Fi"]

### Book Classifications (Many-to-Many via Junction Tables)

#### books ↔ root_genres (Many-to-Many)
- **Relationship**: Books can have multiple root genres, root genres categorize multiple books
- **Cardinality**: N:M
- **Junction Table**: `book_root_genres`
- **Foreign Keys**:
  - `book_root_genres.isbn` → `books.isbn`
  - `book_root_genres.root_id` → `root_genres.root_id`
- **Cascade**: Both ON DELETE CASCADE

#### books ↔ subgenres (Many-to-Many)
- **Relationship**: Books can have multiple subgenres, subgenres categorize multiple books
- **Cardinality**: N:M
- **Junction Table**: `book_subgenres`
- **Foreign Keys**:
  - `book_subgenres.isbn` → `books.isbn`
  - `book_subgenres.subgenre_id` → `subgenres.subgenre_id`
- **Cascade**: Both ON DELETE CASCADE

---

## Table Details

### users
**Purpose**: Store user identity and demographics

**Key Constraints**:
- Primary Key: `user_id` (AUTO_INCREMENT)
- Required: age, age_group, gender, country, has_preferences
- Optional: location, coordinates
- Flags: `has_ratings`, `has_preferences` for quick filtering

**Sample Data**:
```
user_id: 12345
age: 28
age_group: "young_adult_25_34"
gender: "Female"
location: "Seattle, Washington, USA"
country: "USA"
loc_latitude: 47.606209
loc_longitude: -122.332071
```

---

### books
**Purpose**: Core book metadata (reference data)

**Key Constraints**:
- Primary Key: `isbn` (10 characters)
- Required: title, authors, publication_year, publisher
- Optional: genre (some books uncategorized)

**Design Note**: Sparse metadata (price, images, descriptions) moved to MongoDB

**Sample Data**:
```
isbn: "0441172717"
title: "Dune"
authors: "Frank Herbert"
publication_year: 1965
publisher: "Ace Books"
genre: "Science Fiction"
```

---

### ratings
**Purpose**: User-book interaction events

**Key Constraints**:
- Composite Primary Key: (`user_id`, `isbn`)
- Unique: `ratings_seq` (global sequence, AUTO_INCREMENT)
- Foreign Keys: `user_id` → users, `isbn` → books
- Check Constraint: `rating BETWEEN 0 AND 10`

**Sequence Fields**:
- `r_seq_user`: Per-user rating sequence (1st, 2nd, 3rd... rating by this user)
- `r_seq_book`: Per-book rating sequence (1st, 2nd, 3rd... rating for this book)
- Auto-managed by `before_ratings_insert` trigger

**Sample Data**:
```
user_id: 12345
isbn: "0441172717"
rating: 9
ratings_seq: 567890
r_seq_user: 23  (this user's 23rd rating)
r_seq_book: 145 (this book's 145th rating)
r_cat: "highly_engaged"
```

---

### root_genres
**Purpose**: Top-level genre taxonomy

**Key Constraints**:
- Primary Key: `root_id` (AUTO_INCREMENT)
- Unique: `root_name`

**Typical Values**:
```
root_id: 1, root_name: "Fiction"
root_id: 2, root_name: "Non-Fiction"
root_id: 3, root_name: "Young Adult"
```

---

### subgenres
**Purpose**: Specific genre classifications

**Key Constraints**:
- Primary Key: `subgenre_id` (AUTO_INCREMENT)
- Unique: `subgenre_name`
- Foreign Key: `root_id` → root_genres (nullable)

**Typical Values**:
```
subgenre_id: 10, subgenre_name: "Space Opera", root_id: 1 (Fiction)
subgenre_id: 11, subgenre_name: "Cyberpunk", root_id: 1 (Fiction)
subgenre_id: 25, subgenre_name: "Biography", root_id: 2 (Non-Fiction)
```

---

### book_root_genres (Junction)
**Purpose**: Link books to root genres (many-to-many)

**Key Constraints**:
- Composite Primary Key: (`isbn`, `root_id`)
- Foreign Keys: Both cascade delete

**Sample Data**:
```
isbn: "0441172717", root_id: 1  (Dune → Fiction)
isbn: "0441172717", root_id: 3  (Dune → Young Adult)
```

---

### book_subgenres (Junction)
**Purpose**: Link books to specific subgenres (many-to-many)

**Key Constraints**:
- Composite Primary Key: (`isbn`, `subgenre_id`)
- Foreign Keys: Both cascade delete

**Sample Data**:
```
isbn: "0441172717", subgenre_id: 10  (Dune → Space Opera)
isbn: "0441172717", subgenre_id: 15  (Dune → Military SF)
```

---

## Normalization Level

**Third Normal Form (3NF)**:
- No transitive dependencies
- All non-key attributes depend on the primary key
- Junction tables eliminate many-to-many redundancy

**Denormalization Exceptions**:
- `subgenres.root_id`: Included for hierarchical queries (could be derived via joins)
- Justified by query performance for genre filtering

---

## Indexes (Recommended)

```sql
-- Primary keys (automatic)
-- users(user_id), books(isbn), ratings(user_id, isbn)
-- root_genres(root_id), subgenres(subgenre_id)

-- Foreign key indexes (for JOIN performance)
CREATE INDEX idx_ratings_user ON ratings(user_id);
CREATE INDEX idx_ratings_isbn ON ratings(isbn);
CREATE INDEX idx_subgenres_root ON subgenres(root_id);
CREATE INDEX idx_book_root_genres_root ON book_root_genres(root_id);
CREATE INDEX idx_book_subgenres_sub ON book_subgenres(subgenre_id);

-- Query optimization indexes
CREATE INDEX idx_books_year ON books(publication_year);
CREATE INDEX idx_users_country ON users(country);
CREATE INDEX idx_ratings_rating ON ratings(rating);
```

---

## Triggers

### before_ratings_insert
**Purpose**: Auto-increment per-user and per-book rating sequences

**Behavior**:
- Only fires if `r_seq_user` or `r_seq_book` are NULL
- Allows manual setting during bulk loads
- Ensures chronological tracking of rating order

```sql
-- Automatically sets:
-- r_seq_user = (user's previous max + 1) or 1
-- r_seq_book = (book's previous max + 1) or 1
```

---

## Data Integrity Rules

1. **Cannot rate without user**: FK constraint ensures user exists
2. **Cannot rate non-existent book**: FK constraint ensures book exists
3. **Rating range**: CHECK constraint enforces 0-10 scale
4. **One rating per user-book pair**: Composite PK prevents duplicates
5. **Genre hierarchy**: Subgenres optionally link to root genres
6. **Cascade deletes**: Removing user/book removes all related ratings
7. **Orphan prevention**: Junction table FKs prevent orphaned relationships

---

## Viewing the Diagram

### GitHub/GitLab
The Mermaid diagram will render automatically in markdown preview.

### VS Code
Install the "Markdown Preview Mermaid Support" extension.

### Online
Copy the mermaid code block to: https://mermaid.live/

### Alternative: Text Representation

```
users (278K)                    books (271K)
   |                               |
   |                               |
   +---------> ratings <-----------+
               (1.15M)
                                   |
                                   +---> book_root_genres <--- root_genres (3)
                                   |                                |
                                   |                                |
                                   +---> book_subgenres <--- subgenres (50+)
```

---

## Query Examples

### Find all books a user has rated
```sql
SELECT b.title, r.rating, r.r_seq_user
FROM ratings r
JOIN books b ON r.isbn = b.isbn
WHERE r.user_id = 12345
ORDER BY r.r_seq_user DESC;
```

### Find all books in "Science Fiction" genre
```sql
SELECT DISTINCT b.isbn, b.title, b.authors
FROM books b
JOIN book_root_genres brg ON b.isbn = brg.isbn
JOIN root_genres rg ON brg.root_id = rg.root_id
WHERE rg.root_name = 'Fiction';
```

### Find books with multiple genres
```sql
SELECT b.isbn, b.title, COUNT(brg.root_id) as genre_count
FROM books b
JOIN book_root_genres brg ON b.isbn = brg.isbn
GROUP BY b.isbn, b.title
HAVING COUNT(brg.root_id) > 1;
```

### Find subgenres under a root genre
```sql
SELECT s.subgenre_name
FROM subgenres s
JOIN root_genres r ON s.root_id = r.root_id
WHERE r.root_name = 'Fiction'
ORDER BY s.subgenre_name;
```

---

**Schema Version**: 1.0.0  
**Last Updated**: December 2024  
**Database Engine**: InnoDB (MySQL 8.0+)