# Query examples — MySQL, MongoDB and Hybrid

This file contains compact, runnable query examples (simple and complex) for MySQL-only, MongoDB-only and hybrid flows (MySQL + Mongo). Explanations are brief.

---
## MySQL — Simple

1) Top-N highest average rated books (minimum 10 ratings)
```sql
SELECT b.isbn, b.title,
       AVG(r.rating) AS avg_rating,
       COUNT(r.rating) AS num_ratings
FROM books b
JOIN ratings r USING (isbn)
GROUP BY b.isbn, b.title
HAVING COUNT(r.rating) >= 10
ORDER BY avg_rating DESC
LIMIT 10;
```

2) User rating history (most recent) 
```sql
SELECT r.user_id, r.isbn, r.rating, r.created_at
FROM ratings r
WHERE r.user_id = 12345
ORDER BY r.created_at DESC
LIMIT 50;
```

## MySQL — Complex

1) Find users most similar to a given user by overlapping positively-rated books (co-rated, simple similarity)
- idea: count common books with rating >= 7 for target user
```sql
WITH target AS (
  SELECT isbn FROM ratings WHERE user_id = 12345 AND rating >= 7
)
SELECT r.user_id, COUNT(*) AS common_good
FROM ratings r
JOIN target t USING (isbn)
WHERE r.user_id <> 12345 AND r.rating >= 7
GROUP BY r.user_id
ORDER BY common_good DESC
LIMIT 20;
```

2) Candidate ranking using collaborative popularity: recommend books liked by similar users but not seen by target
```sql
WITH similar AS (
  SELECT r.user_id, COUNT(*) AS common_good
  FROM ratings r
  JOIN (SELECT isbn FROM ratings WHERE user_id = 12345 AND rating>=7) t USING (isbn)
  WHERE r.user_id <> 12345 AND r.rating >= 7
  GROUP BY r.user_id
  ORDER BY common_good DESC
  LIMIT 200
),
candidates AS (
  SELECT cr.isbn, AVG(cr.rating) AS mean_rating, COUNT(cr.rating) AS cnt
  FROM ratings cr
  JOIN similar s ON cr.user_id = s.user_id
  WHERE cr.isbn NOT IN (SELECT isbn FROM ratings WHERE user_id = 12345)
  GROUP BY cr.isbn
)
SELECT c.isbn, c.mean_rating, c.cnt
FROM candidates c
WHERE c.cnt >= 3
ORDER BY c.mean_rating DESC, c.cnt DESC
LIMIT 50;
```

Notes:
- These run purely in MySQL; performance benefits from indexes on ratings(user_id,isbn,rating).

---
## MongoDB — Simple

1) Get user's profile (preferences + last ratings)
```javascript
db.user_profiles.findOne({ user_id: 12345 }, { preferences:1, summary:1, rating_history: { $slice: 20 } })
```

2) Top books by aggregated rating stored in book_details
```javascript
db.book_details.find({ "aggregates.num_ratings": { $gte: 10 } })
  .sort({ "aggregates.avg_rating": -1 })
  .limit(10)
  .project({ isbn:1, "metadata.title":1, "aggregates":1 });
```

## MongoDB — Complex

1) Content-based candidate retrieval: find books similar by genres and tags, score by tag overlap
```javascript
// pipeline: for a given isbn, get top similar books by shared genres/tags
const targetIsbn = "0345417953";
db.book_details.aggregate([
  { $match: { isbn: targetIsbn } },
  { $project: { genres: "$metadata.genres", tags: 1 } },
  { $lookup: {
      from: "book_details",
      let: { g: "$genres", t: "$tags" },
      pipeline: [
        { $match: { isbn: { $ne: targetIsbn } } },
        { $project: {
            isbn:1, title: "$title", genres: "$metadata.genres", tags:1,
            commonGenres: { $size: { $setIntersection: ["$metadata.genres", "$$g"] } },
            commonTags:   { $size: { $setIntersection: ["$tags", "$$t"] } }
        }},
        { $match: { $expr: { $gt: [ { $add: ["$commonGenres", "$commonTags"] }, 0 ] } } },
        { $sort: { commonGenres:-1, commonTags:-1, "aggregates.avg_rating": -1 } },
        { $limit: 50 }
      ],
      as: "candidates"
  }},
  { $project: { candidates: 1 } }
])
```

2) Aggregation: Top authors in user's preferred genres
```javascript
db.user_profiles.aggregate([
  { $match: { user_id: 12345 } },
  { $unwind: "$preferences.preferred_genres" },
  { $lookup: {
      from: "book_details",
      localField: "preferences.preferred_genres.name",
      foreignField: "metadata.genres",
      as: "genre_books"
  }},
  { $unwind: "$genre_books" },
  { $group: { _id: "$genre_books.authors", count: { $sum: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 20 }
])
```

Notes:
- Use text indexes and multikey indexes described in schema to speed these pipelines.

---
## Hybrid queries (MySQL + MongoDB)

Pattern: fetch core IDs or structured aggregates from MySQL, then enrich / filter with MongoDB, or vice versa.

### Hybrid — Simple
Goal: Get MySQL user info + Mongo preference summary in one response (app layer combines).
Steps:
1) SQL: get user row
```sql
SELECT user_id, age, country_iso2 FROM users WHERE user_id = 12345;
```
2) Mongo: get user profile
```javascript
db.user_profiles.findOne({ user_id: 12345 }, { summary:1, preferences:1 });
```
Combine in application: merge fields, return unified user view.

### Hybrid — Complex
Goal: Produce top-N hybrid recommendations:
- Use MongoDB to get user's top preferred genres/authors.
- Use MySQL to compute candidate book popularity & availability (joins & ratings).
- Combine scores and rank.

Steps (conceptual + queries):

1) Mongo: get top genres for user (fast)
```javascript
const profile = db.user_profiles.findOne({ user_id: 12345 }, { "summary.favorite_genres":1 });
const topGenres = (profile?.summary?.favorite_genres || []).slice(0,3);
```

2) MySQL: get candidate books in these genres with popularity and avg rating
Assume a mapping table book_genres (or use books.genre if denormalized); example using books.genre:
```sql
SELECT b.isbn, b.title,
       IFNULL(agg.avg_rating,0) AS avg_rating,
       IFNULL(agg.num_ratings,0) AS num_ratings
FROM books b
LEFT JOIN (
  SELECT isbn, AVG(rating) AS avg_rating, COUNT(*) AS num_ratings
  FROM ratings
  GROUP BY isbn
) agg USING (isbn)
WHERE b.isbn IN (
  -- optional: get ISBNs from Mongo results if you queried book_details by genre first
)
AND (b.genre IN ('Science Fiction','Space Opera'))    -- use topGenres here
ORDER BY avg_rating DESC, num_ratings DESC
LIMIT 200;
```

3) Mongo: further re-rank candidates by content-similarity / personalized metadata (apply text/tag overlap)
```javascript
// Pull candidate ISBN array from SQL result, then:
db.book_details.aggregate([
  { $match: { isbn: { $in: [ "isbn1", "isbn2", "isbn3", ... ] } } },
  { $project: {
      isbn:1, title:1, "metadata.genres":1, tags:1, "aggregates.avg_rating":1,
      score_content: { $add: [ { $size: { $setIntersection: ["$metadata.genres", topGenres] } }, { $size: { $setIntersection: ["$tags", user_top_tags || []] } } ] }
  }},
  { $sort: { score_content: -1, "aggregates.avg_rating": -1 } },
  { $limit: 20 }
])
```

4) Application: combine SQL popularity score and Mongo content score into final ranking:
final_score = alpha * normalized_sql_score + beta * normalized_content_score

Notes:
- Keep candidate sets bounded (e.g., 200) to avoid large transfers.
- Use background jobs to precompute candidate lists or store them in recommendation_cache for ultra-fast serving.

---
## Indexing & operational tips

- MySQL: indexes on ratings(user_id, isbn, rating), books(isbn, genre), ratings(isbn) improve join and aggregation performance.
- MongoDB: ensure indexes described in schema (isbn,user_id,text,indexes) exist.
- When doing hybrid queries, prefer:
  - fetch small ID sets from DB A, then lookup details in DB B
  - avoid large cross-joins across systems in real-time
  - use precomputed caches (recommendation_cache) for interactive latency

```// filepath: /home/pfanyka/Desktop/MASTERS/Database_ADV/book_rec_project/db/queries.md
# Query examples — MySQL, MongoDB and Hybrid

This file contains compact, runnable query examples (simple and complex) for MySQL-only, MongoDB-only and hybrid flows (MySQL + Mongo). Explanations are brief.

---
## MySQL — Simple

1) Top-N highest average rated books (minimum 10 ratings)
```sql
SELECT b.isbn, b.title,
       AVG(r.rating) AS avg_rating,
       COUNT(r.rating) AS num_ratings
FROM books b
JOIN ratings r USING (isbn)
GROUP BY b.isbn, b.title
HAVING COUNT(r.rating) >= 10
ORDER BY avg_rating DESC
LIMIT 10;
```

2) User rating history (most recent)
```sql
SELECT r.user_id, r.isbn, r.rating, r.created_at
FROM ratings r
WHERE r.user_id = 12345
ORDER BY r.created_at DESC
LIMIT 50;
```

## MySQL — Complex

1) Find users most similar to a given user by overlapping positively-rated books (co-rated, simple similarity)
- idea: count common books with rating >= 7 for target user
```sql
WITH target AS (
  SELECT isbn FROM ratings WHERE user_id = 12345 AND rating >= 7
)
SELECT r.user_id, COUNT(*) AS common_good
FROM ratings r
JOIN target t USING (isbn)
WHERE r.user_id <> 12345 AND r.rating >= 7
GROUP BY r.user_id
ORDER BY common_good DESC
LIMIT 20;
```

2) Candidate ranking using collaborative popularity: recommend books liked by similar users but not seen by target
```sql
WITH similar AS (
  SELECT r.user_id, COUNT(*) AS common_good
  FROM ratings r
  JOIN (SELECT isbn FROM ratings WHERE user_id = 12345 AND rating>=7) t USING (isbn)
  WHERE r.user_id <> 12345 AND r.rating >= 7
  GROUP BY r.user_id
  ORDER BY common_good DESC
  LIMIT 200
),
candidates AS (
  SELECT cr.isbn, AVG(cr.rating) AS mean_rating, COUNT(cr.rating) AS cnt
  FROM ratings cr
  JOIN similar s ON cr.user_id = s.user_id
  WHERE cr.isbn NOT IN (SELECT isbn FROM ratings WHERE user_id = 12345)
  GROUP BY cr.isbn
)
SELECT c.isbn, c.mean_rating, c.cnt
FROM candidates c
WHERE c.cnt >= 3
ORDER BY c.mean_rating DESC, c.cnt DESC
LIMIT 50;
```

Notes:
- These run purely in MySQL; performance benefits from indexes on ratings(user_id,isbn,rating).

---
## MongoDB — Simple

1) Get user's profile (preferences + last ratings)
```javascript
db.user_profiles.findOne({ user_id: 12345 }, { preferences:1, summary:1, rating_history: { $slice: 20 } })
```

2) Top books by aggregated rating stored in book_details
```javascript
db.book_details.find({ "aggregates.num_ratings": { $gte: 10 } })
  .sort({ "aggregates.avg_rating": -1 })
  .limit(10)
  .project({ isbn:1, "metadata.title":1, "aggregates":1 });
```

## MongoDB — Complex

1) Content-based candidate retrieval: find books similar by genres and tags, score by tag overlap
```javascript
// pipeline: for a given isbn, get top similar books by shared genres/tags
const targetIsbn = "0345417953";
db.book_details.aggregate([
  { $match: { isbn: targetIsbn } },
  { $project: { genres: "$metadata.genres", tags: 1 } },
  { $lookup: {
      from: "book_details",
      let: { g: "$genres", t: "$tags" },
      pipeline: [
        { $match: { isbn: { $ne: targetIsbn } } },
        { $project: {
            isbn:1, title: "$title", genres: "$metadata.genres", tags:1,
            commonGenres: { $size: { $setIntersection: ["$metadata.genres", "$$g"] } },
            commonTags:   { $size: { $setIntersection: ["$tags", "$$t"] } }
        }},
        { $match: { $expr: { $gt: [ { $add: ["$commonGenres", "$commonTags"] }, 0 ] } } },
        { $sort: { commonGenres:-1, commonTags:-1, "aggregates.avg_rating": -1 } },
        { $limit: 50 }
      ],
      as: "candidates"
  }},
  { $project: { candidates: 1 } }
])
```

2) Aggregation: Top authors in user's preferred genres
```javascript
db.user_profiles.aggregate([
  { $match: { user_id: 12345 } },
  { $unwind: "$preferences.preferred_genres" },
  { $lookup: {
      from: "book_details",
      localField: "preferences.preferred_genres.name",
      foreignField: "metadata.genres",
      as: "genre_books"
  }},
  { $unwind: "$genre_books" },
  { $group: { _id: "$genre_books.authors", count: { $sum: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 20 }
])
```

Notes:
- Use text indexes and multikey indexes described in schema to speed these pipelines.

---
## Hybrid queries (MySQL + MongoDB)

Pattern: fetch core IDs or structured aggregates from MySQL, then enrich / filter with MongoDB, or vice versa.

### Hybrid — Simple
Goal: Get MySQL user info + Mongo preference summary in one response (app layer combines).
Steps:
1) SQL: get user row
```sql
SELECT user_id, age, country_iso2 FROM users WHERE user_id = 12345;
```
2) Mongo: get user profile
```javascript
db.user_profiles.findOne({ user_id: 12345 }, { summary:1, preferences:1 });
```
Combine in application: merge fields, return unified user view.

### Hybrid — Complex
Goal: Produce top-N hybrid recommendations:
- Use MongoDB to get user's top preferred genres/authors.
- Use MySQL to compute candidate book popularity & availability (joins & ratings).
- Combine scores and rank.

Steps (conceptual + queries):

1) Mongo: get top genres for user (fast)
```javascript
const profile = db.user_profiles.findOne({ user_id: 12345 }, { "summary.favorite_genres":1 });
const topGenres = (profile?.summary?.favorite_genres || []).slice(0,3);
```

2) MySQL: get candidate books in these genres with popularity and avg rating
Assume a mapping table book_genres (or use books.genre if denormalized); example using books.genre:
```sql
SELECT b.isbn, b.title,
       IFNULL(agg.avg_rating,0) AS avg_rating,
       IFNULL(agg.num_ratings,0) AS num_ratings
FROM books b
LEFT JOIN (
  SELECT isbn, AVG(rating) AS avg_rating, COUNT(*) AS num_ratings
  FROM ratings
  GROUP BY isbn
) agg USING (isbn)
WHERE b.isbn IN (
  -- optional: get ISBNs from Mongo results if you queried book_details by genre first
)
AND (b.genre IN ('Science Fiction','Space Opera'))    -- use topGenres here
ORDER BY avg_rating DESC, num_ratings DESC
LIMIT 200;
```

3) Mongo: further re-rank candidates by content-similarity / personalized metadata (apply text/tag overlap)
```javascript
// Pull candidate ISBN array from SQL result, then:
db.book_details.aggregate([
  { $match: { isbn: { $in: [ "isbn1", "isbn2", "isbn3", ... ] } } },
  { $project: {
      isbn:1, title:1, "metadata.genres":1, tags:1, "aggregates.avg_rating":1,
      score_content: { $add: [ { $size: { $setIntersection: ["$metadata.genres", topGenres] } }, { $size: { $setIntersection: ["$tags", user_top_tags || []] } } ] }
  }},
  { $sort: { score_content: -1, "aggregates.avg_rating": -1 } },
  { $limit: 20 }
])
```

4) Application: combine SQL popularity score and Mongo content score into final ranking:
final_score = alpha * normalized_sql_score + beta * normalized_content_score

Notes:
- Keep candidate sets bounded (e.g., 200) to avoid large transfers.
- Use background jobs to precompute candidate lists or store them in recommendation_cache for ultra-fast serving.

---
## Indexing & operational tips

- MySQL: indexes on ratings(user_id, isbn, rating), books(isbn, genre), ratings(isbn) improve join and aggregation performance.
- MongoDB: ensure indexes described in schema (isbn,user_id,text,indexes) exist.
- When doing hybrid queries, prefer:
  - fetch small ID sets from DB A, then lookup details in DB B
  - avoid large cross-joins across systems in real-time
  - use precomputed caches (recommendation_cache) for interactive latency
