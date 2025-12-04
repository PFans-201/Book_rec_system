# Book Recommendation System - Query Catalog

This document describes various recommendation queries that leverage both MySQL (structured data) and MongoDB (flexible document data) in our hybrid database architecture.

## Query Categories

### 1. Simple Queries (Single Database)
Basic queries using either MySQL or MongoDB alone.

### 2. Complex Queries (Multi-Database)
Advanced queries that join data across MySQL and MongoDB for rich recommendations.

### 3. Hybrid Queries (Cross-Database)
Queries that combine relational integrity from MySQL with document flexibility from MongoDB.

---

## Simple Queries

### S1: Popular Books by Genre
**Database**: MySQL  
**Description**: Find most-rated books in a specific genre.
```sql
SELECT b.isbn, b.title, b.authors, COUNT(r.rating) as rating_count
FROM books b
JOIN book_root_genres brg ON b.isbn = brg.isbn
JOIN root_genres rg ON brg.root_id = rg.root_id
JOIN ratings r ON b.isbn = r.isbn
WHERE rg.root_name = 'Fiction'
GROUP BY b.isbn, b.title, b.authors
ORDER BY rating_count DESC
LIMIT 10;
```

### S2: User Reading History
**Database**: MySQL  
**Description**: Get a user's reading history with ratings.
```sql
SELECT b.title, b.authors, r.rating, r.r_cat, r.r_seq_user
FROM ratings r
JOIN books b ON r.isbn = b.isbn
WHERE r.user_id = 12345
ORDER BY r.r_seq_user DESC
LIMIT 20;
```

### S3: Books by Price Range
**Database**: MongoDB  
**Description**: Find books within a specific price range with good ratings.
```javascript
db.books_metadata.find({
  "extra_metadata.price_usd": { $gte: 10, $lte: 25 },
  "rating_metrics.r_avg": { $gte: 7 }
}).sort({ "rating_metrics.rating_score": -1 }).limit(10)
```

### S4: User Profile Summary
**Database**: MongoDB  
**Description**: Get detailed user profile with preferences.
```javascript
db.users_profiles.findOne({ _id: 12345 })
```

---

## Complex Queries

### C1: Content-Based Recommendations
**Databases**: MySQL + MongoDB  
**Description**: Recommend books similar to what user has rated highly, considering genre, author, and price preferences.
**Script**: `recommendations/recommendation_content_based.py`

**Logic**:
1. Get user's highly-rated books from MySQL
2. Extract common genres/authors
3. Fetch user preferences from MongoDB
4. Find similar books matching criteria
5. Filter by price range and rating quality

### C2: Collaborative Filtering Recommendations
**Databases**: MySQL + MongoDB  
**Description**: Find users with similar tastes and recommend what they liked.
**Script**: `recommendations/recommendation_collaborative.py`

**Logic**:
1. Find users who rated similar books similarly (MySQL)
2. Get their other highly-rated books
3. Enrich with metadata and ratings from MongoDB
4. Rank by similarity score and book quality

### C3: Geographic Recommendations
**Databases**: MySQL + MongoDB  
**Description**: Recommend books popular in user's region or similar regions.
**Script**: `recommendations/recommendation_geographic.py`

**Logic**:
1. Find users in similar locations (using lat/long from MySQL)
2. Aggregate their highly-rated books
3. Fetch book metadata and popularity from MongoDB
4. Rank by regional popularity

### C4: Hybrid Personalized Recommendations
**Databases**: MySQL + MongoDB  
**Description**: Combine content-based, collaborative, and popularity signals.
**Script**: `recommendations/recommendation_hybrid.py`

**Logic**:
1. Content similarity score (genre/author match)
2. Collaborative filtering score (similar users)
3. Global popularity score (from MongoDB metrics)
4. User preference alignment score
5. Weighted combination of all signals

### C5: Cold-Start Recommendations (New Users)
**Databases**: MySQL + MongoDB  
**Description**: Recommend books to users with few/no ratings based on demographics and global trends.
**Script**: `recommendations/recommendation_cold_start.py`

**Logic**:
1. Find users with similar demographics (age_group, gender) from MySQL
2. Get their top-rated books
3. Boost with global popularity from MongoDB
4. Filter by availability and recency

### C6: Diversity-Aware Recommendations
**Databases**: MySQL + MongoDB  
**Description**: Provide diverse recommendations across multiple genres/authors.
**Script**: `recommendations/recommendation_diverse.py`

**Logic**:
1. Get user's reading history from MySQL
2. Identify under-explored genres/authors
3. Sample top books from diverse categories
4. Balance familiar vs. exploratory recommendations

### C7: Trending Books Recommendations
**Databases**: MySQL + MongoDB  
**Description**: Recommend currently trending books with recent activity.
**Script**: `recommendations/recommendation_trending.py`

**Logic**:
1. Find books with recent ratings (last N ratings per book from MySQL)
2. Calculate recent activity score
3. Fetch popularity metrics from MongoDB
4. Rank by trend score (velocity + quality)

### C8: Similar Books Recommendation
**Databases**: MySQL + MongoDB  
**Description**: Find books similar to a given book.
**Script**: `recommendations/recommendation_similar_books.py`

**Logic**:
1. Get target book's genres/authors from MySQL
2. Find books sharing genres/subgenres
3. Fetch metadata and ratings from MongoDB
4. Calculate similarity score
5. Rank by similarity and quality

---

## Hybrid Queries

### H1: User-Book Compatibility Score
**Databases**: MySQL + MongoDB  
**Description**: Calculate how well a book matches a user's profile.
**Script**: `recommendations/query_compatibility_score.py`

**Metrics**:
- Genre match (user preferences vs book genres)
- Author familiarity
- Price fit
- Rating quality
- Popularity alignment with user's reader level

### H2: Recommendation Explanation
**Databases**: MySQL + MongoDB  
**Description**: Explain why a book is recommended to a user.
**Script**: `recommendations/query_recommendation_explanation.py`

**Factors**:
- Shared genres with user favorites
- Similar author
- Popular in user's region
- Liked by similar users
- Matches price preference

### H3: User Taste Evolution
**Databases**: MySQL + MongoDB  
**Description**: Analyze how user's reading preferences have changed over time.
**Script**: `recommendations/query_taste_evolution.py`

**Analysis**:
- Genre distribution over time (using r_seq_user from MySQL)
- Rating patterns evolution
- Price sensitivity changes
- Author diversity progression

### H4: Book Recommendation Dashboard
**Databases**: MySQL + MongoDB  
**Description**: Generate comprehensive recommendation report for a user.
**Script**: `recommendations/query_recommendation_dashboard.py`

**Includes**:
- Top personalized recommendations
- Trending in user's interests
- Hidden gems (high quality, low popularity)
- New releases in favorite genres
- Books from favorite authors

---

## Performance Optimization Notes

1. **MySQL Indexes**: Ensure indexes on (user_id, isbn), (isbn), genre junction tables
2. **MongoDB Indexes**: Create indexes on rating_metrics, popularity_metrics, extra_metadata.price_usd
3. **Caching**: Cache user preferences and popular book lists
4. **Batch Processing**: When computing recommendations for many users, batch MongoDB queries
5. **Materialized Views**: Consider caching recommendation results for active users

---

## Query Execution Guidelines

1. **Always validate input** (user_id, isbn existence)
2. **Set reasonable limits** (default 10-20 recommendations)
3. **Handle edge cases** (new users, niche books)
4. **Log query performance** for optimization
5. **Consider fallbacks** (when primary recommendation fails, use popularity)

---

## Example Usage

```bash
# Run specific recommendation query
python scripts/recommendations/recommendation_content_based.py --user_id 12345 --limit 10

# Run hybrid recommendations
python scripts/recommendations/recommendation_hybrid.py --user_id 12345 \
  --content_weight 0.4 --collab_weight 0.4 --popularity_weight 0.2

# Run update scripts
python scripts/insert_new_data.py
python scripts/update_ratings_preferences.py

# Generate dashboard
python scripts/recommendations/query_recommendation_dashboard.py --user_id 12345
```

For detailed usage examples, see `scripts/recommendations/README.md`

---

## Future Enhancements 

1. Real-time recommendation updates via change streams
2. A/B testing framework for recommendation algorithms
3. Multi-objective optimization (accuracy + diversity + novelty)
4. Deep learning-based embeddings for books and users
5. Session-based recommendations
6. Contextual recommendations (time of day, season)
