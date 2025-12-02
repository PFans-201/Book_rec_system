# Entity-Relationship (ER) diagram

This document sketches the database logical model for the Book Recommendation System.

## Entities and attributes

1. **User**
   - `user_id` (PK, integer)
   - `age` (integer, nullable)
   - `location` (string, nullable)

2. **Book**
   - `isbn` (PK, string)
   - `title` (string, nullable)
   - `author` (string, nullable)
   - `year` (integer, nullable)
   - `publisher` (string, nullable)

3. **Rating**
   - `id` (PK, integer, auto-increment)
   - `user_id` (FK → User.user_id, cascade delete)
   - `isbn` (FK → Book.isbn, cascade delete)
   - `rating` (float)
   - Unique constraint: (user_id, isbn)

## Relationships

- **User 1:N Rating** — one user can rate many books.
- **Book 1:N Rating** — one book can be rated by many users.

In relational terms:
- `Rating.user_id` references `User.user_id` (ON DELETE CASCADE)
- `Rating.isbn` references `Book.isbn` (ON DELETE CASCADE)

## Normalization notes

This schema is in **3NF (Third Normal Form)**:
- All non-key attributes depend solely on the primary key.
- There are no transitive dependencies:
  - `User` has no multi-valued or derived attributes.
  - `Book` metadata (title, author, year, publisher) all relate directly to the ISBN.
  - `Rating` composite attributes (user_id, isbn, rating) are minimal and relevant; the rating score is a fact about the (user, book) pair.

## Diagram (text-based)

```
+--------+            1:N          +----------+           N:1          +--------+
| User   |--------------------->  | Rating   | <--------------------| Book   |
+--------+                         +----------+                       +--------+
| user_id (PK)                     | id (PK)                         | isbn (PK)
| age                              | user_id (FK)                    | title
| location                         | isbn (FK)                       | author
                                   | rating                          | year
                                                                     | publisher
```

## Indexes

- `books.author`, `books.title` — for lookups and text searches.
- `ratings.user_id`, `ratings.isbn`, `ratings.rating` — support joins and aggregations.
- Unique index on `ratings(user_id, isbn)` to prevent duplicate ratings.

This simple ER design supports efficient joins for recommendation and analytics queries while keeping data normalized and easy to maintain.
