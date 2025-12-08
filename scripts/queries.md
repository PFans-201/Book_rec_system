# Book Recommendation System - Query Catalog

This document describes various recommendation queries that leverage both 
MySQL (structured data) and MongoDB (flexible document data) in our hybrid 
database architecture.

## Query Categories

### 1. Simple Queries (Single Database)
Basic queries using either MySQL or MongoDB alone.

### 2. Complex Queries (Multi-table/collection)
Advanced queries that join data across multiple tables in MySQL, 
or multiple collections in MongoDB for rich recommendations.

### 3. Hybrid Queries (Cross-Database)
Queries that combines information from federated operations, by joining 
data from relational database with document data, taking advantage of both data models.

---

>**NOTE:** the next queries only include the description. The actual 
implementation is stored in [`query_helper.py`](queries/query_helper.py), 
with the following [execution guide](queries/Query_execution.md).
the
## Simple Queries

The following queries are great for quick lookups or basic recommendations.
Additionally this can work for any type of user (with or wihout preferences 
and/or ratings). These queries provide content-based (using book attributes 
like price) and popularity-based (using rating counts or scoring methods) recommendations.

### S1: top_books
**Database**: MySQL  
**Description**: Popularity-based recommendation: find top books with highest number of rating counts
**Variables**: limit
```sql
SELECT isbn, COUNT(*) AS rating_count
FROM ratings
ORDER BY rating_count DESC
LIMIT %(limit)s;  -- Maximum number of recommendations
```

### S1 (MongoDB version): top_books
**Database**: MongoDB  
**Description**: Popularity-based recommendation: find top M books with highest number of rating counts
**Variables**: limit
**Difference**: Uses pre-computed rating metric (total number of ratings, explicit or implicit) per book, saving computation time. Might be faster than MySQL version for large databases (e.g., millions of ratings). Although requires periodic updates to keep metrics fresh.
```javascript
bookrec.books_metadata.aggregate([
  { $sort: { "rating_metrics.r_total": -1 } },
  { $limit: limit },
  { $project: {
      isbn: "$_id",
      r_total: "$rating_metrics.r_total",
      _id: 0
    }
  }])
``` 

### S2: price_range
**Database**: MongoDB  
**Description**: Content and Popularity-based recommendation: find top M books within a specific price (H, L for high and low bound for price) range with good ratings.
**Variables**: low, high, min_avg, limit
```javascript
bookrec.books_metadata.aggregate([
  { $match: {
      "extra_metadata.price_usd": { $gte: low, $lte: high },
      "rating_metrics.r_avg": { $gte: min_avg }
    }
  },
  { $sort: { "rating_metrics.rating_score": -1 } },
  { $limit: limit },
  { $project: {
      isbn: "$_id",
      price_usd: "$extra_metadata.price_usd",
      r_avg: "$rating_metrics.r_avg",
      rating_score: "$rating_metrics.rating_score",
      _id: 0
    }
  }
])
// Rating score is a weighted average of r_avg considering r_count (support) and r_std (variability)
```

## Complex Queries

These queries involve multiple tables or collections to produce richer recommendations, .
They can be used for more complex recommendation filtering or even user specific queries.
**Note:** Actual code in [`query_helper.py`](queries/query_helper.py).

### C1: top_recent_books

**Database**: MySQL  
**Description**: More complex popularity-based recommendation: find top best rated books with at least S ratings and average rating greater than or equal to A, considering only the N most recent ratings; and providing not only the isbn but also the books' title and authors when joining with books table.
**Variables**: limit, min_supt, min_avg, n_recent

### C2: Collaborative recommendation (Geo -> Demographic -> Global Fallback)
(for short: collaborative_geographic)
**Database**: MySQL  
**Description**: Tries to find similar users by location + age. If location is missing or no neighbors found, falls back to age group only. If that fails, returns globally popular books.
**Variables**: user_id, min_avg, proximity_radius (km), limit

#### The Haversine Formula
To calculate the great-circle distance between two points on a sphere given their longitudes and latitudes, we use the Haversine formula:

$$
d = 2r \cdot \arcsin\left(\sqrt{\sin^2\left(\frac{\phi_2 - \phi_1}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\lambda_2 - \lambda_1}{2}\right)}\right)
$$

**Where:**
* $d$: Distance between the two points
* $r$: Radius of the Earth ($\approx 6371$ km)
* $\phi_1, \phi_2$: Latitude of point 1 and 2 (in radians)
* $\lambda_1, \lambda_2$: Longitude of point 1 and 2 (in radians)

```sql
WITH target_user AS (
    SELECT age_group, loc_latitude, loc_longitude
    FROM users
    WHERE user_id = %(user_id)s
),
-- Strategy 1: Geographic Neighbors (requires lat/long)
geo_neighbors AS (
    SELECT u.user_id
    FROM users u
    JOIN target_user tu ON u.age_group = tu.age_group
    WHERE u.user_id != %(user_id)s
      AND tu.loc_latitude IS NOT NULL AND tu.loc_longitude IS NOT NULL
      AND u.loc_latitude IS NOT NULL AND u.loc_longitude IS NOT NULL
      AND (
        6371 * 2 * ASIN(SQRT(
            POWER(SIN(RADIANS(u.loc_latitude - tu.loc_latitude) / 2), 2) +
            COS(RADIANS(tu.loc_latitude)) * COS(RADIANS(u.loc_latitude)) *
            POWER(SIN(RADIANS(u.loc_longitude - tu.loc_longitude) / 2), 2)
        ))
      ) <= %(proximity_radius)s

), -- rest of the code
```

#### Usage of Spatial Indexing

**MySQL** native **`SPATIAL INDEX`** supports spherical geometry natively without needing to type out the Haversine formula manually.

By using MySQL's native Spatial functions, the previous complex query becomes incredibly simple and **much faster** because it can actually use the index, whereas the manual formula **cannot** use an index and will force a full table scan.

#### How to implement SPATIAL INDEX in MySQL

**Step 1: The Table Setup**
Instead of separate `latitude` and `longitude` float columns, you use a single `POINT` column and add a `SPATIAL` index.

```sql
ALTER TABLE users ADD COLUMN geopoint POINT;
-- Update existing data usually (Longitude, Latitude) in functions
UPDATE users SET geopoint = POINT(loc_longitude, loc_latitude); 

-- This creates an R-Tree index (similar to 2dsphere from MongoDB)
ALTER TABLE users MODIFY geopoint POINT NOT NULL;
CREATE SPATIAL INDEX idx_geopoint ON users(geopoint);
```

**Step 2: The Optimized Query**
(for short: collaborative_geographic_INDEX)
MySQL provides the `ST_Distance_Sphere` function, optimized C++ calculation for the distance.

```sql
WITH target_user AS (
    SELECT age_group, geopoint
    FROM users
    WHERE user_id = %(user_id)s
),
nearby_users AS (
    SELECT u.user_id
    FROM users u
    JOIN target_user tu ON u.age_group = tu.age_group
    WHERE u.user_id != %(user_id)s
      -- native function: calculates distance in meters
      AND ST_Distance_Sphere(u.geopoint, tu.geopoint) <= (%(proximity_radius)s * 1000) 
)WITH target_user AS (
    SELECT age_group, geopoint
    FROM users
    WHERE user_id = %(user_id)s
),
-- Strategy 1: Geographic Neighbors (using SPATIAL index)
geo_neighbors AS (
    SELECT u.user_id
    FROM users u
    JOIN target_user tu ON u.age_group = tu.age_group
    WHERE u.user_id != %(user_id)s
      AND u.geopoint IS NOT NULL 
      AND tu.geopoint IS NOT NULL
      -- ST_Distance_Sphere returns meters, so: (radius (km) * 1000) (m)
      -- Less lines of code + more readable than Haversine formula
      AND ST_Distance_Sphere(u.geopoint, tu.geopoint) <= (%(proximity_radius)s * 1000)

), -- rest of the code
```

**Benefits:**
1.  **Performance:** `ST_Distance_Sphere` coupled with a `SPATIAL INDEX` should be 
faster than the manual Haversine math `(SIN/COS/ACOS...)` because the database can prune the search space efficiently.
2.  **Cleanliness:** It reduces 10 lines of error-prone math into 1 function call.

### C3: genre_collaborative
**Database:** MySQL
**Description:** Finds the top rated books from book genres read by users in the same age group and gender as the target user.
1.  **Identify Neighbors**: Users with same `age_group` and `gender`.
2.  **Find Popular Genres**: Aggregates the genres of books rated highly by these neighbors.
3.  **Recommend Books**: Returns top books from those popular genres (excluding books the target user has already read).
**Variables:** user_id, limit, min_avg, min_supt

### C4: user_profile_recommendation
**Database**: MongoDB  
**Description**: Demographic recommendation: finds books matching a specific user's 
profile preferences (genres, authors, publishers, years) and reading level. It 
calculates a personalized score by boosting books that match existent preferences 
and have high popularity. Handles comma-separated preference strings.
**Variables**: user_id, limit

---

## Hybrid Query

This can be used for highly personalized recommendations by leveraging both MySQL and MongoDB data. Combining information from both databases allows for richer and more accurate recommendations. We can include user preferences and extra book metadata (sparse data), and computed metrics from MongoDB along with structured user and book data from MySQL.

**Note:** actual code in [query_helper.py](queries/query_helper.py)

### hybrid_personalized

**Databases**: MySQL + MongoDB  
**Description**: Combines Collaborative Filtering (MySQL) and Content-Based Filtering (MongoDB).
1. **MySQL**: Finds books rated highly by similar users (Demographic neighbors in same age group, and Geographic neighbors within proximity radius if location data exists).
2. **MongoDB**: Finds books matching the user's specific preferences (Authors, Years, and Publishers).
3. **Merge**: Joins on ISBN and calculates a final weighted score.

> **Note**: The final scoring logic `(collab_score * w1) + (content_score * w2)` (for example) is performed in the application layer (Pandas) after the join.

#### Strategy
*   **Left Query (MySQL)**: Returns `isbn` and `collab_score` (based on neighbor ratings).
*   **Right Query (MongoDB)**: Returns `isbn` and `content_score` (based on preference matching).
*   **Join**: Outer Join on `isbn` (to include books found by either strategy).

### H1: hybrid_personalized (Standard)
- Uses the standard Haversine formula for the MySQL geographic component.

### H2: hybrid_personalized_spatial (Optimized)
**MySQL Variables**: user_id, limit, proximity_radius, min_avg
- Uses MySQL `SPATIAL INDEX` and `ST_Distance_Sphere` for the geographic component, offering better performance on large user datasets.
**MongDB implementation:** Same for H1 and H2
**MongDB variables:** user_id, limit

---

## Performance Optimization Considerations:

1. **MySQL Indexes** and **MongoDB Indexes**: Create indexes on frequently queried columns/fields to speed up lookups.
2. **Caching**: Cache user preferences and popular book lists
3. **Batch Processing**: When computing recommendations for many users, batch MongoDB queries
4. **Materialized Views**: Consider caching recommendation results for active users

