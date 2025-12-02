# MongoDB Schema — Book Recommendation System

This document describes recommended MongoDB collections, key fields, example documents and indexes. MongoDB stores flexible enrichment and cached / precomputed artifacts that complement the core MySQL schema.

## Collections:
- user_profiles: flexible user metadata, preference summaries, reading history
- book_details: extended book metadata, aggregated ratings, tags
- recommendation_cache: per-user precomputed recommendations (TTL-capable)

**Notes:**
- Keep MySQL as source of truth for transactional core (users, books, ratings). 
- Use MongoDB for enrichment, denormalized views and fast retrieval for recommendations.
- Store shared keys (user_id, isbn) so joining/enrichment is straightforward.

---

### `user_profiles` 

TODO: NEEDS IMPROVEMENT BECAUSE OF PREFERENCES
AND OTHER USER PROFILING LIKE:
- type of rater by amount (casual, avid, critic)
- type of rater by rating value (unkown for only one rating, harsh, lenient, neutral)
    - the latter might influence a recommendation for a books with more ratings that gives a more accurate measure of overal rating score than a book with the same score but less ratings even though we are going to use weighted avg

**Purpose:** per-user preference summaries and lightweight history for quick lookups.

Example document:
```json
{
  "_id": ObjectId("..."),
  "user_id": 12345,                // integer, matches MySQL.users.user_id
  "summary": {
    "avg_rating": 7.4,
    "total_ratings": 42,
    "favorite_genres": ["Science Fiction","Mystery"],
    "favorite_authors": ["Isaac Asimov"]
  },
  "preferences": {
    "preferred_genres": [{"name":"Science Fiction","score":0.62}],
    "preferred_authors": [{"name":"Asimov","score":0.25}]
  },
  "rating_history": [              // optional short history; keep bounded (e.g., last 200)
    {"isbn":"0345417953", "rating":8, "ts": ISODate("2024-10-01T12:00:00Z")}
  ],
  "location": {
    "city":"Seattle",
    "state":"WA",
    "country_iso2":"US",
    "loc": { "type": "Point", "coordinates": [-122.3321, 47.6062] } // GeoJSON lon,lat
  },
  "updated_at": ISODate("2025-11-16T08:00:00Z")
}
```

**Recommended indexes:**
- { user_id: 1 } unique
- { "location.loc": "2dsphere" } for geo queries (if geospatial use)
- { "summary.favorite_genres": 1 } (multikey) if querying by genre preference

**Storage guidelines:**
- Keep rating_history bounded (cap array or maintain separate collection for full event log).
- Use numeric scores for preferences to enable ranking.

---

### `book_details`

**Purpose:** extended metadata, tags, aggregated ratings and optional reviews.

Example document:
```json
{
  "_id": ObjectId("..."),
  "isbn": "0345417953",            // matches MySQL.books.isbn
  "title": "Example Title",
  "authors": ["Author One", "Author Two"],
  "metadata": {
    "publisher": "Penguin",
    "publication_date": ISODate("1997-07-01T00:00:00Z"),
    "genres": ["Science Fiction","Space Opera"],
  },
  "aggregates": {
    "avg_rating": 4.2,
    "num_ratings": 1234,
    "num_reviews": 120
  },
  "tags": ["space", "future", "classic"],
  "reviews_sample": [               // optional bounded sample
    {"user_id": 222, "rating": 9, "text": "Great read", "ts": ISODate("2025-01-10")}
  ],
  "updated_at": ISODate("2025-11-16T08:00:00Z")
}
```

**Recommended indexes:**
- { isbn: 1 } unique
- { "metadata.genres": 1 } (multikey)
- { "aggregates.avg_rating": -1, "aggregates.num_ratings": -1 } for popularity queries
- Text index on title/authors/tags: { title: "text", authors: "text", tags: "text" }

---

### `recommendation_cache`

**Purpose:** store per-user precomputed recommendations for fast retrieval. Use TTL if recommendations are ephemeral.

Example document:
```json
{
  "_id": ObjectId("..."),
  "user_id": 12345,
  "candidates": [
    { "isbn": "0345417953", "score": 9.2, "reason": "hybrid_cf", "meta": { "neighbors": [456,789] } },
    { "isbn": "0441013597", "score": 8.7, "reason": "content_sim" }
  ],
  "model_version": "v1.2",
  "computed_at": ISODate("2025-11-16T08:00:00Z"),
  "expires_at": ISODate("2025-11-17T08:00:00Z")  // optional TTL control
}
```

**Recommended indexes:**
- { user_id: 1 } unique
- { expires_at: 1 } with expireAfterSeconds: 0 if using TTL??

---

## Operational notes

- Keep denormalized aggregates (avg_rating, num_ratings) updated by a background job consuming rating events (or periodic batch).
- Use MongoDB for:
  - fast per-user recommendation retrieval
  - flexible storage of variable metadata (tags, external metadata)
  - caching/experiment records (model_version)
- Use MySQL for:
  - transactional data, referential integrity and analytics requiring joins/ACID guarantees
