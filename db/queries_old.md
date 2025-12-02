# Query Design and Implementation

- Design queries and operations that power a basic recommendation system
(must include simple and complex queries).
- MySQL should handle structured analytics (e.g., top-rated items, user history).
- MongoDB should handle contextual or preference-based queries (e.g., user
interests, item attributes).
- Implement at least one combined or federated operation where data from both
systems contribute to a recommendation (e.g., fetching user data from MySQL
and preference data from MongoDB).


**Deliverables** (to show in class):
● SQL and MongoDB queries with documentation
● Examples of query outputs
● Explanation of how each query supports recommendations

## Hybrid Database for Book Recommendation System

### MySQL Queries

1. **Top-N Rated Books**:
```sql
SELECT b.isbn, b.title, AVG(r.rating) AS avg_rating, COUNT(r.rating) AS num_ratings
FROM books b
JOIN ratings r ON b.isbn = r.isbn -- sort-merge join for efficiency?
GROUP BY b.isbn, b.title
HAVING COUNT(r.rating) >= 10
ORDER BY avg_rating DESC
LIMIT 10;