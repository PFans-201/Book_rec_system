-- Advanced Postgres SQL: stored procedures, recursive CTEs, and advanced analytics

--------------------------------------------------------------------------------
-- 1) Stored procedure: insert a rating (or update if exists), return inserted/updated id
--------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION upsert_rating(
  p_user_id INTEGER,
  p_isbn TEXT,
  p_rating REAL
) RETURNS INTEGER AS $$
DECLARE
  v_id INTEGER;
BEGIN
  INSERT INTO ratings(user_id, isbn, rating)
  VALUES (p_user_id, p_isbn, p_rating)
  ON CONFLICT (user_id, isbn) DO UPDATE
    SET rating = EXCLUDED.rating
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- Usage example:
-- SELECT upsert_rating(12345, '0345417953', 9.0);


--------------------------------------------------------------------------------
-- 2) Recursive CTE: find chain of "influence" (users who rated a set of similar books)
--    This example recursively finds users who share at least 2 books with a seed user,
--    then who share books with those users, etc., up to depth 3.
--------------------------------------------------------------------------------
WITH RECURSIVE user_chain AS (
  -- Base case: starting user
  SELECT 12345 AS user_id, 0 AS depth
  UNION
  -- Recursive case: find users who share 2+ books with current layer, limit depth
  SELECT DISTINCT r2.user_id, uc.depth + 1
  FROM user_chain uc
  JOIN ratings r1 ON r1.user_id = uc.user_id
  JOIN ratings r2 ON r2.isbn = r1.isbn AND r2.user_id <> uc.user_id
  WHERE uc.depth < 3
  GROUP BY r2.user_id, uc.depth
  HAVING COUNT(DISTINCT r1.isbn) >= 2
)
SELECT * FROM user_chain
ORDER BY depth, user_id
LIMIT 100;


--------------------------------------------------------------------------------
-- 3) Materialized view: top 100 books by explicit average rating (min 20 ratings)
--    Refreshed on demand for dashboards/reports.
--------------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_top_books AS
WITH agg AS (
  SELECT r.isbn,
         AVG(NULLIF(r.rating, 0)) AS avg_rating,
         COUNT(*) FILTER (WHERE r.rating <> 0) AS n_explicit
  FROM ratings r
  GROUP BY r.isbn
)
SELECT b.isbn, b.title, b.author, a.avg_rating, a.n_explicit
FROM agg a
JOIN books b USING (isbn)
WHERE a.n_explicit >= 20
ORDER BY a.avg_rating DESC NULLS LAST
LIMIT 100;

-- Create an index on the materialized view for fast lookups by isbn
CREATE INDEX IF NOT EXISTS mv_top_books_isbn_idx ON mv_top_books(isbn);

-- Refresh (call periodically after data updates):
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_top_books;


--------------------------------------------------------------------------------
-- 4) Complex window function: rank users by activity within age brackets
--------------------------------------------------------------------------------
SELECT user_id,
       age,
       COUNT(*) OVER (PARTITION BY user_id) AS user_ratings,
       DENSE_RANK() OVER (
         PARTITION BY CASE
           WHEN age < 18 THEN '<18'
           WHEN age < 30 THEN '18-29'
           WHEN age < 50 THEN '30-49'
           ELSE '50+'
         END
         ORDER BY COUNT(*) OVER (PARTITION BY user_id) DESC
       ) AS rank_in_age_group
FROM ratings r
JOIN users u USING (user_id)
WHERE u.age IS NOT NULL
ORDER BY age, rank_in_age_group
LIMIT 100;


--------------------------------------------------------------------------------
-- 5) Aggregate + lateral join: for each user, show top 3 genres (via co-rated authors)
--    (This is illustrative; extend with a real genre/author taxonomy if available)
--------------------------------------------------------------------------------
WITH user_author_counts AS (
  SELECT r.user_id, b.author, COUNT(*) AS n
  FROM ratings r
  JOIN books b USING (isbn)
  WHERE b.author IS NOT NULL
  GROUP BY r.user_id, b.author
)
SELECT u.user_id, t.author, t.n
FROM users u
CROSS JOIN LATERAL (
  SELECT author, n
  FROM user_author_counts uac
  WHERE uac.user_id = u.user_id
  ORDER BY n DESC
  LIMIT 3
) t
WHERE u.user_id IN (SELECT user_id FROM ratings GROUP BY user_id HAVING COUNT(*) >= 10)
LIMIT 100;
