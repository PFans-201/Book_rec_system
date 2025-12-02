# MongoDB Schema Documentation

This document describes the MongoDB collections and document structures for the Book Recommendation System.

---

## Collections Overview

| Collection Name       | Purpose                                          | Key Field(s)       |
|-----------------------|--------------------------------------------------|--------------------|
| `user_profiles`       | User preferences, reading history, behavioral data | `user_id` (unique) |
| `book_details`        | Extended book metadata, reviews, categories      | `isbn` (unique)    |
| `recommendation_cache`| Pre-computed recommendations for users           | `user_id` (unique) |

---

## 1. `user_profiles`

**Purpose**: Store flexible, evolving user data that doesn't fit well in relational tables.

**Document Schema**:
```javascript
{
  _id: ObjectId("..."),
  user_id: 12345,  // Links to MySQL users.user_id
  rating_summary: {
    avg_rating: 7.5, // we could create a categorical variable based on this avg rating, like harsh, moderate, lenient rater
    total_ratings: 42,
  },
  preferences: {
    // if good ratings are really scattered across different genres, authors, publishers, years of publication, book lengths user might not have strong preferences

    // We might want to include preference thresholds to indicate strength of preference by proportion of ratings in each category, for example: 80% of good ratings in a genre indicates strong preference in this genre, so that one user has 1 preferred author, and an other user has 3 preferred authors

    favorite_books: ["0345417953", "0441013597", ...], // got from some analysis
    preferred_genres: ["Science Fiction", "Mystery"],   // need to have google books API genre mapping
    preferred_authors: ["Isaac Asimov", "Arthur C. Clarke"], //got from some analysis
    preferred_publishers: ["Penguin Random House", "HarperCollins"], // got from some analysis
    preferred_years_of_publication: { min: 1950, max: 2020 }, // range of years got from some analysis
  },
  rating_history: [
    {
      isbn: "0345417953",
      rating: 8,
    },
    // ... more entries
  ],
  rating_distribution: { // to be revised
    "0" : 2,
    "1" : 0,
    // until
    "10": 15
  },
  location: { //teacher wants spatial index (longitude, latitude) or (city, state, country), or both
    city: "New York", //this at the momment look like this: "nyc, new york, usa
    state: "NY",
    country: "USA",
    longitude: -74.0060, // retrieved through some geocoding API or specific script designed by us?
    latitude: 40.7128
  }
}
```

<!-- **Indexes**:
```javascript
db.user_profiles.createIndex({ user_id: 1 }, { unique: true });
``` -->

---

## 2. `book_details`

**Purpose**: Store extended book metadata that's too flexible/nested for MySQL.

**Document Schema**:
```javascript
{
  _id: ObjectId("..."),
  isbn: "0345417953",  // Links to MySQL books.isbn
  metadata: {
    genre: ["Science Fiction", "Classic", "Adventure", "Space Opera"], // by merging with another dataset
    avg_rating: 8.9,
    num_ratings: 1234,
    publication_date: ISODate("1979-10-12T00:00:00Z"), //can be other data formats
    publisher: "Mass Market Paperback",
  },
  ratings: [ //should we keep it?
    {
      user_id: 12345,
      rating: 9,
    },
    // ... more reviews
  ]
}
```

<!-- **Indexes**:
```javascript
db.book_details.createIndex({ isbn: 1 }, { unique: true });
db.book_details.createIndex({ "extended_metadata.categories": 1 });
db.book_details.createIndex({ "extended_metadata.avg_rating": -1 });
db.book_details.createIndex({ tags: 1 });
``` -->
---

## 3. `recommendation_cache`

**Purpose**: Store pre-computed recommendations for fast retrieval.

**Document Schema**:
```javascript
{
  _id: ObjectId("..."),
  user_id: 12345,  // Links to MySQL users.user_id
  recommendations: [
    {
      // colaborative filtering to give 10 most relevant books
      isbn: "0345417953",
      score: 9.2,
      reason: "collaborative_filtering",
      metadata: { neighbors: ["user456", "user789"] }
    },
    {
      isbn: "0441013597",
      score: 8.7,
      reason: "content_based",
      metadata: { similar_to: ["0345417953"] }
    },

    //include hybrid approaches
    // ... top-N recommendations
  ]
}
```

**Indexes**:
```javascript
db.recommendation_cache.createIndex({ user_id: 1 }, { unique: true });
db.recommendation_cache.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0 }); // TTL index
```

---

## Integration with MySQL

**Shared Keys**:
- `user_id`: Present in both MySQL `users` table and MongoDB `user_profiles`, `interaction_logs`, `recommendation_cache`
- `isbn`: Present in both MySQL `books` table and MongoDB `book_details`, `interaction_logs`

**Data Flow**:
1. **MySQL** stores structured, normalized, transactional data (users, books, ratings)
2. **MongoDB** stores flexible, nested, behavioral data (preferences, reviews, events)
3. Queries can:
   - Start in MySQL (get user/book core data)
   - Enrich with MongoDB (add preferences, extended metadata, recent interactions)
   - Or vice versa

**Example Hybrid Query Flow**:
```python
# 1. Get user from MySQL
user = mysql_session.query(User).filter_by(user_id=12345).first()

# 2. Enrich with MongoDB profile
user_profile = mongo_db.user_profiles.find_one({"user_id": 12345})

# 3. Combine for complete user view
combined = {
    "user_id": user.user_id,
    "age": user.age,
    "location": user.location,
    "preferences": user_profile["preferences"],
    "reading_history": user_profile["reading_history"]
}
```

---

## Schema Evolution

MongoDB's flexible schema allows adding new fields without migrations:
- Add `user_profiles.subscription_tier` → no ALTER TABLE needed
- Add nested `book_details.awards` array → just insert documents with new structure
- Change `interaction_logs.metadata` structure per event type → no constraints

This flexibility complements MySQL's rigid structure, giving the best of both worlds.
