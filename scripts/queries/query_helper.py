import json
import copy
import time
import pandas as pd  
import copy
import re

# ==========================================
# PART 1: THE QUERY REPOSITORY
# ==========================================
QUERIES = {
    'Simple': {
        "MySQL": {
            'top_books': {
                'description': "Popularity-based recommendation: find top books with highest number of rating counts",
                'type': 'select', 
                'variables': ['limit'],
                'query': """
                    SELECT isbn, COUNT(*) AS rating_count
                    FROM ratings
                    GROUP BY isbn
                    ORDER BY rating_count DESC
                    LIMIT %(limit)s;
                """
            }
        },
        "MongoDB": {
            'top_books': {
                'description': "Popularity-based recommendation: find top books with highest number of rating counts",
                'type': 'aggregate',
                'collection': 'books_metadata',
                'variables': ['limit'],
                'pipeline': [
                    { "$sort": { "rating_metrics.rating_count": -1 } },
                    { "$limit": "__LIMIT__" },
                    { "$project": {
                        "isbn": "$_id",
                        "rating_count": "$rating_metrics.rating_count",
                        "_id": 0
                    }}
                ]
            },
            'price_range': {
                'description': "Find top M books within price range (Low/High) with good avg rating",
                'type': 'aggregate',
                'collection': 'books_metadata',  # only 1 collection to gatter information from
                'variables': ['low', 'high', 'min_avg', 'limit'],
                # placeholders replaced by _inject_params_into_pipeline()
                'pipeline': [
                    { "$match": {
                        "extra_metadata.price_usd": { "$gte": "__LOW__", "$lte": "__HIGH__" },
                        "rating_metrics.r_avg": { "$gte": "__MIN_AVG__" }
                    }},
                    { "$sort": { "rating_metrics.rating_score": -1 } },
                    { "$limit": "__LIMIT__" },
                    { "$project": {
                        "isbn": "$_id",
                        "price_usd": "$extra_metadata.price_usd",
                        "r_avg": "$rating_metrics.r_avg",
                        "rating_score": "$rating_metrics.rating_score",
                        "_id": 0
                    }}
                ]
            }
        }
    },
    'Complex': {
        "MySQL": {
            'top_recent_books': {
                'description': "More complex popularity-based recommendation: find top best rated books with at least S ratings and average rating greater than or equal to A, considering only the N most recent ratings; and providing not only the isbn but also the books' title and authors when joining with books table.",
                'type': 'select',
                'variables': ['limit', 'min_supt', 'min_avg', 'n_recent'],
                'query': """
                    WITH latest_ratings AS (
                        SELECT
                            r.isbn,
                            r.rating,
                            ROW_NUMBER() OVER (PARTITION BY r.isbn ORDER BY r.ratings_seq DESC) AS rn
                        FROM ratings r
                        WHERE r.rating > 0 
                    ),
                    topN AS (
                        SELECT isbn, rating
                        FROM latest_ratings
                        WHERE rn <= %(n_recent)s 
                    ),
                    book_stats AS (
                        SELECT
                            isbn,
                            COUNT(*)    AS rating_count,
                            AVG(rating) AS avg_rating
                        FROM topN
                        GROUP BY isbn
                        HAVING COUNT(*) >= %(min_supt)s    
                            AND AVG(rating) >= %(min_avg)s 
                    )
                    SELECT
                        b.isbn,
                        b.title,
                        b.authors,
                        bs.rating_count,
                        bs.avg_rating
                    FROM book_stats bs
                    JOIN books b USING (isbn)
                    ORDER BY bs.avg_rating DESC, bs.rating_count DESC
                    LIMIT %(limit)s;  
                """
            },
            'collaborative_geographic': {
                'description': "Recommend books by location+age, falling back to age-only, then global popularity",
                'type': 'select',
                'variables': ['user_id', 'min_avg', 'proximity_radius', 'limit'],
                'query': """
                    WITH target_user AS (
                        SELECT age_group, loc_latitude, loc_longitude
                        FROM users
                        WHERE user_id = %(user_id)s
                    ),
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
                    ),
                    demo_neighbors AS (
                        SELECT u.user_id
                        FROM users u
                        JOIN target_user tu ON u.age_group = tu.age_group
                        WHERE u.user_id != %(user_id)s
                        LIMIT 100
                    ),
                    recs AS (
                        SELECT 
                            1 as priority, b.isbn, b.title, b.authors,
                            COUNT(r.rating) as rating_count, AVG(r.rating) as avg_rating
                        FROM ratings r
                        JOIN books b ON r.isbn = b.isbn
                        WHERE r.user_id IN (SELECT user_id FROM geo_neighbors) AND r.rating > 0
                        GROUP BY b.isbn, b.title, b.authors
                        HAVING avg_rating >= %(min_avg)s

                        UNION ALL

                        SELECT 
                            2 as priority, b.isbn, b.title, b.authors,
                            COUNT(r.rating) as rating_count, AVG(r.rating) as avg_rating
                        FROM ratings r
                        JOIN books b ON r.isbn = b.isbn
                        WHERE r.user_id IN (SELECT user_id FROM demo_neighbors) AND r.rating > 0
                          AND NOT EXISTS (SELECT 1 FROM geo_neighbors)
                        GROUP BY b.isbn, b.title, b.authors
                        HAVING avg_rating >= %(min_avg)s

                        UNION ALL

                        SELECT 
                            3 as priority, b.isbn, b.title, b.authors,
                            COUNT(r.rating) as rating_count, AVG(r.rating) as avg_rating
                        FROM ratings r
                        JOIN books b ON r.isbn = b.isbn
                        WHERE r.rating > 0
                          AND NOT EXISTS (SELECT 1 FROM geo_neighbors)
                          AND NOT EXISTS (SELECT 1 FROM demo_neighbors)
                        GROUP BY b.isbn, b.title, b.authors
                        HAVING avg_rating >= %(min_avg)s
                    )
                    SELECT isbn, title, authors, rating_count, avg_rating
                    FROM recs
                    ORDER BY priority ASC, avg_rating DESC, rating_count DESC
                    LIMIT %(limit)s;
                """
            },
            "collaborative_geographic_INDEX" : {
                'description': "Needs Spatial Index: Recommends books by location+age, falling back to age-only, then global popularity",
                'type': 'select',
                'variables': ['user_id', 'min_avg', 'proximity_radius', 'limit'],
                'query': """
                    WITH target_user AS (
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
                        -- ST_Distance_Sphere returns meters, so multiply radius km * 1000
                        AND ST_Distance_Sphere(u.geopoint, tu.geopoint) <= (%(proximity_radius)s * 1000)
                    ),
                    -- Strategy 2: Demographic Neighbors (Age Group only) - used if Geo fails
                    demo_neighbors AS (
                        SELECT u.user_id
                        FROM users u
                        JOIN target_user tu ON u.age_group = tu.age_group
                        WHERE u.user_id != %(user_id)s
                        LIMIT 100 -- Limit sample size for performance
                    ),
                    -- Calculate recommendations for all strategies
                    recs AS (
                        -- 1. Geo Recommendations
                        SELECT 
                            1 as priority,
                            b.isbn, b.title, b.authors,
                            COUNT(r.rating) as rating_count,
                            AVG(r.rating) as avg_rating
                        FROM ratings r
                        JOIN books b ON r.isbn = b.isbn
                        WHERE r.user_id IN (SELECT user_id FROM geo_neighbors)
                        AND r.rating > 0
                        GROUP BY b.isbn, b.title, b.authors
                        HAVING avg_rating >= %(min_avg)s

                        UNION ALL

                        -- 2. Demographic Recommendations (Fallback)
                        SELECT 
                            2 as priority,
                            b.isbn, b.title, b.authors,
                            COUNT(r.rating) as rating_count,
                            AVG(r.rating) as avg_rating
                        FROM ratings r
                        JOIN books b ON r.isbn = b.isbn
                        WHERE r.user_id IN (SELECT user_id FROM demo_neighbors)
                        AND r.rating > 0
                        AND NOT EXISTS (SELECT 1 FROM geo_neighbors) -- Only run if Geo failed
                        GROUP BY b.isbn, b.title, b.authors
                        HAVING avg_rating >= %(min_avg)s

                        UNION ALL

                        -- 3. Global Popularity (Ultimate Fallback)
                        SELECT 
                            3 as priority,
                            b.isbn, b.title, b.authors,
                            COUNT(r.rating) as rating_count,
                            AVG(r.rating) as avg_rating
                        FROM ratings r
                        JOIN books b ON r.isbn = b.isbn
                        WHERE r.rating > 0
                        AND NOT EXISTS (SELECT 1 FROM geo_neighbors)
                        AND NOT EXISTS (SELECT 1 FROM demo_neighbors)
                        GROUP BY b.isbn, b.title, b.authors
                        HAVING avg_rating >= %(min_avg)s
                    )
                    SELECT isbn, title, authors, rating_count, avg_rating
                    FROM recs
                    ORDER BY priority ASC, avg_rating DESC, rating_count DESC
                    LIMIT %(limit)s;
                """
            },
            'genre_collaborative': {
                'description': "Recommend books from genres popular among users of same age/gender.",
                'type': 'select',
                'variables': ['user_id', 'limit', 'min_avg', 'min_supt'],
                'query': """
                    WITH target_user AS (
                        SELECT age_group, gender
                        FROM users
                        WHERE user_id = %(user_id)s
                    ),
                    -- 1. Find Demographic Neighbors
                    neighbors AS (
                        SELECT u.user_id
                        FROM users u
                        JOIN target_user tu ON u.age_group = tu.age_group AND u.gender = tu.gender
                        WHERE u.user_id != %(user_id)s
                    ),
                    -- 2. Find Top Genres among Neighbors (Root Genres)
                    top_genres AS (
                        SELECT 
                            brg.root_id,
                            COUNT(r.rating) as genre_popularity
                        FROM ratings r
                        JOIN book_root_genres brg ON r.isbn = brg.isbn
                        WHERE r.user_id IN (SELECT user_id FROM neighbors)
                          AND r.rating >= %(min_avg)s
                        GROUP BY brg.root_id
                        ORDER BY genre_popularity DESC
                        LIMIT 5 -- Focus on top 5 genres
                    ),
                    -- 3. Recommend Books from these Genres
                    candidate_books AS (
                        SELECT 
                            b.isbn, 
                            b.title, 
                            b.authors,
                            AVG(r.rating) as avg_rating,
                            COUNT(r.rating) as rating_count
                        FROM books b
                        JOIN book_root_genres brg ON b.isbn = brg.isbn
                        JOIN ratings r ON b.isbn = r.isbn
                        WHERE brg.root_id IN (SELECT root_id FROM top_genres)
                          AND r.rating > 0
                          -- Exclude books read by target user
                          AND b.isbn NOT IN (SELECT isbn FROM ratings WHERE user_id = %(user_id)s)
                        GROUP BY b.isbn, b.title, b.authors
                        HAVING rating_count >= %(min_supt)s 
                           AND avg_rating >= %(min_avg)s
                    )
                    SELECT isbn, title, authors, rating_count, avg_rating
                    FROM candidate_books
                    ORDER BY avg_rating DESC, rating_count DESC
                    LIMIT %(limit)s;
                """
            }
        },
        "MongoDB": {
            'user_profile_recommendation': {
                'description': "Personalized recommendation using user profile (preferences & reading level). Handles comma-separated preference strings.",
                'type': 'aggregate',
                'collection': 'users_profiles',
                'variables': ['user_id', 'limit'],
                'pipeline': [
                    { "$match": { "_id": "__USER_ID__" } },
                    # Pre-process: Split comma-separated strings into arrays
                    { "$addFields": {
                        "preferences.pref_root_genres_arr": { 
                            "$split": [{ "$ifNull": ["$preferences.pref_root_genres", ""] }, ","] 
                        },
                        "preferences.pref_authors_arr": { 
                            "$split": [{ "$ifNull": ["$preferences.pref_authors", ""] }, ","] 
                        },
                        "preferences.pref_publishers_arr": { 
                            "$split": [{ "$ifNull": ["$preferences.pref_publisher", ""] }, ","] 
                        },
                        "preferences.pref_years_arr": { 
                            "$split": [{ "$ifNull": ["$preferences.pref_pub_year", ""] }, ","] 
                        }
                    }},
                    { "$lookup": {
                        "from": "books_metadata",
                        "let": {
                            "p_root": "$preferences.pref_root_genres_arr",
                            "p_sub":  { "$ifNull": ["$preferences.pref_subgenres", []] },
                            "p_authors": "$preferences.pref_authors_arr",
                            "p_publishers": "$preferences.pref_publishers_arr",
                            "p_years": "$preferences.pref_years_arr",
                            "p_min":  { "$ifNull": ["$preferences.pref_price_min", 0] },
                            "p_max":  { "$ifNull": ["$preferences.pref_price_max", 1000] },
                            "p_avg_rating": { "$ifNull": ["$profile.mean_rating", 0] }
                        },
                        "pipeline": [
                            { "$match": {
                                "$expr": {
                                    "$and": [
                                        # A. Genre Overlap (Root) - Must match at least one if preferences exist
                                        { "$or": [
                                            { "$eq": [{ "$size": "$$p_root" }, 0] },
                                            { "$eq": [{ "$arrayElemAt": ["$$p_root", 0] }, ""] },
                                            { "$gt": [{ "$size": { "$setIntersection": ["$extra_metadata.root_genres", "$$p_root"] } }, 0] }
                                        ]},
                                        # B. Price Range
                                        { "$or": [
                                            { "$eq": ["$extra_metadata.price_usd", None] },
                                            { "$and": [
                                                { "$gte": ["$extra_metadata.price_usd", "$$p_min"] },
                                                { "$lte": ["$extra_metadata.price_usd", "$$p_max"] }
                                            ]}
                                        ]},
                                        # C. Quality Filter
                                        { "$gte": ["$rating_metrics.r_avg", "$$p_avg_rating"] }
                                    ]
                                }
                            }},
                            { "$addFields": {
                                "personal_score": {
                                    "$add": [
                                        { "$ifNull": ["$rating_metrics.rating_score", 0] },
                                        # Bonus: Subgenre Match (+2.0)
                                        { "$cond": [
                                            { "$gt": [{ "$size": { "$setIntersection": ["$extra_metadata.subgenres", "$$p_sub"] } }, 0] },
                                            2.0, 0.0
                                        ]},
                                        # Bonus: Author Match (+3.0)
                                        { "$cond": [
                                            { "$in": ["$extra_metadata.author", "$$p_authors"] }, 
                                            3.0, 0.0
                                        ]},
                                        # Bonus: Publisher Match (+1.0)
                                        { "$cond": [
                                            { "$in": ["$extra_metadata.publisher", "$$p_publishers"] }, 
                                            1.0, 0.0
                                        ]},
                                        # Bonus: Year Match (+1.0)
                                        { "$cond": [
                                            { "$in": [{ "$toString": "$extra_metadata.publication_year" }, "$$p_years"] }, 
                                            1.0, 0.0
                                        ]},
                                        # Bonus: Popularity
                                        { "$ifNull": ["$popularity_metrics.popularity", 0] }
                                    ]
                                }
                            }},
                            { "$sort": { "personal_score": -1 } },
                            { "$limit": "__LIMIT__" }
                        ],
                        "as": "recs"
                    }},
                    { "$unwind": "$recs" },
                    { "$project": {
                        "isbn": "$recs._id",
                        "score": "$recs.personal_score",
                        "title": "$recs.title",
                        "price": "$recs.extra_metadata.price_usd",
                        "genres": "$recs.extra_metadata.root_genres",
                        "rating_avg": "$recs.rating_metrics.r_avg",
                        "_id": 0
                    }}
                ]
            }
        }
    },
    'Hybrid': {
        'hybrid_personalized': {
            'description': "Hybrid Merge: MySQL (Collab/Geo Haversine) + MongoDB (Content/Profile). Returns merged scores.",
            'type': 'join',
            'variables': ['user_id', 'min_avg', 'proximity_radius', 'limit'],
            'join_keys': {'left': 'isbn', 'right': 'isbn'},
            'how': 'outer', 
            
            # 1. MySQL: Find books via Neighbors (Standard Haversine)
            'left_query': {
                'db_type': 'MySQL',
                'query': """
                    WITH target_user AS (
                        SELECT age_group, loc_latitude, loc_longitude
                        FROM users
                        WHERE user_id = %(user_id)s
                    ),
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
                    ),
                    demo_neighbors AS (
                        SELECT u.user_id
                        FROM users u
                        JOIN target_user tu ON u.age_group = tu.age_group
                        WHERE u.user_id != %(user_id)s
                        LIMIT 100
                    ),
                    recs AS (
                        -- Geo Priority
                        SELECT b.isbn, AVG(r.rating) as collab_score
                        FROM ratings r
                        JOIN books b ON r.isbn = b.isbn
                        WHERE r.user_id IN (SELECT user_id FROM geo_neighbors) AND r.rating > 0
                        GROUP BY b.isbn
                        HAVING collab_score >= %(min_avg)s
                        
                        UNION ALL
                        
                        -- Demo Fallback
                        SELECT b.isbn, AVG(r.rating) as collab_score
                        FROM ratings r
                        JOIN books b ON r.isbn = b.isbn
                        WHERE r.user_id IN (SELECT user_id FROM demo_neighbors) AND r.rating > 0
                        GROUP BY b.isbn
                        HAVING collab_score >= %(min_avg)s
                    )
                    SELECT isbn, MAX(collab_score) as collab_score 
                    FROM recs 
                    GROUP BY isbn
                    ORDER BY collab_score DESC 
                    LIMIT %(limit)s;
                """
            },
            
            # 2. MongoDB: Find books via Preferences (Authors, Years, Publishers)
            'right_query': {
                'db_type': 'MongoDB',
                'collection': 'users_profiles',
                'variables': ['user_id', 'limit'],
                'pipeline': [
                    { "$match": { "_id": "__USER_ID__" } },
                    # Split strings into arrays for matching
                    { "$addFields": {
                        "preferences.pref_authors_arr": { 
                            "$split": [{ "$ifNull": ["$preferences.pref_authors", ""] }, ","] 
                        },
                        "preferences.pref_publishers_arr": { 
                            "$split": [{ "$ifNull": ["$preferences.pref_publisher", ""] }, ","] 
                        },
                        "preferences.pref_years_arr": { 
                            "$split": [{ "$ifNull": ["$preferences.pref_pub_year", ""] }, ","] 
                        }
                    }},
                    { "$lookup": {
                        "from": "books_metadata",
                        "let": {
                            "p_sub":  { "$ifNull": ["$preferences.pref_subgenres", []] },
                            "p_authors": "$preferences.pref_authors_arr",
                            "p_publishers": "$preferences.pref_publishers_arr",
                            "p_years": "$preferences.pref_years_arr",
                            "p_avg_rating": { "$ifNull": ["$profile.mean_rating", 0] }
                        },
                        "pipeline": [
                            { "$match": {
                                "$expr": {
                                    "$and": [
                                        # A. Must match at least one specific preference (Author OR Publisher OR Year)
                                        { "$or": [
                                            { "$in": ["$extra_metadata.author", "$$p_authors"] },
                                            { "$in": ["$extra_metadata.publisher", "$$p_publishers"] },
                                            { "$in": [{ "$toString": "$extra_metadata.publication_year" }, "$$p_years"] }
                                        ]},
                                        # B. Quality Filter (Optional: keep books above user's average rating)
                                        { "$gte": ["$rating_metrics.r_avg", "$$p_avg_rating"] }
                                    ]
                                }
                            }},
                            { "$addFields": {
                                "content_score": {
                                    "$add": [
                                        { "$ifNull": ["$rating_metrics.rating_score", 0] },
                                        # Bonus: Subgenre Match (+2.0) - kept for scoring boost even if not filtering
                                        { "$cond": [
                                            { "$gt": [{ "$size": { "$setIntersection": ["$extra_metadata.subgenres", "$$p_sub"] } }, 0] },
                                            2.0, 0.0
                                        ]},
                                        # Bonus: Author Match (+3.0)
                                        { "$cond": [
                                            { "$in": ["$extra_metadata.author", "$$p_authors"] }, 
                                            3.0, 0.0
                                        ]},
                                        # Bonus: Publisher Match (+1.0)
                                        { "$cond": [
                                            { "$in": ["$extra_metadata.publisher", "$$p_publishers"] }, 
                                            1.0, 0.0
                                        ]},
                                        # Bonus: Year Match (+1.0)
                                        { "$cond": [
                                            { "$in": [{ "$toString": "$extra_metadata.publication_year" }, "$$p_years"] }, 
                                            1.0, 0.0
                                        ]},
                                        # Bonus: Popularity
                                        { "$ifNull": ["$popularity_metrics.popularity", 0] }
                                    ]
                                }
                            }},
                            { "$sort": { "content_score": -1 } },
                            { "$limit": "__LIMIT__" }
                        ],
                        "as": "recs"
                    }},
                    { "$unwind": "$recs" },
                    { "$project": {
                        "isbn": "$recs._id",
                        "content_score": "$recs.content_score",
                        "title": "$recs.title",
                        "_id": 0
                    }}
                ]
            }
        },
        'hybrid_personalized_INDEX': {
            'description': "Hybrid Merge: MySQL (Collab/Geo Spatial Index) + MongoDB (Content/Profile). Returns merged scores.",
            'type': 'join',
            'variables': ['user_id', 'min_avg', 'proximity_radius', 'limit'],
            'join_keys': {'left': 'isbn', 'right': 'isbn'},
            'how': 'outer', 
            
            # 1. MySQL: Find books via Neighbors (Spatial Index)
            'left_query': {
                'db_type': 'MySQL',
                'query': """
                    WITH target_user AS (
                        SELECT age_group, geopoint
                        FROM users
                        WHERE user_id = %(user_id)s
                    ),
                    geo_neighbors AS (
                        SELECT u.user_id
                        FROM users u
                        JOIN target_user tu ON u.age_group = tu.age_group
                        WHERE u.user_id != %(user_id)s
                          AND u.geopoint IS NOT NULL AND tu.geopoint IS NOT NULL
                          AND ST_Distance_Sphere(u.geopoint, tu.geopoint) <= (%(proximity_radius)s * 1000)
                    ),
                    demo_neighbors AS (
                        SELECT u.user_id
                        FROM users u
                        JOIN target_user tu ON u.age_group = tu.age_group
                        WHERE u.user_id != %(user_id)s
                        LIMIT 100
                    ),
                    recs AS (
                        -- Geo Priority
                        SELECT b.isbn, AVG(r.rating) as collab_score
                        FROM ratings r
                        JOIN books b ON r.isbn = b.isbn
                        WHERE r.user_id IN (SELECT user_id FROM geo_neighbors) AND r.rating > 0
                        GROUP BY b.isbn
                        HAVING collab_score >= %(min_avg)s
                        
                        UNION ALL
                        
                        -- Demo Fallback
                        SELECT b.isbn, AVG(r.rating) as collab_score
                        FROM ratings r
                        JOIN books b ON r.isbn = b.isbn
                        WHERE r.user_id IN (SELECT user_id FROM demo_neighbors) AND r.rating > 0
                        GROUP BY b.isbn
                        HAVING collab_score >= %(min_avg)s
                    )
                    SELECT isbn, MAX(collab_score) as collab_score 
                    FROM recs 
                    GROUP BY isbn
                    ORDER BY collab_score DESC 
                    LIMIT %(limit)s;
                """
            },
            
            # 2. MongoDB: Same as above (reused logic)
            # 2. MongoDB: Find books via Preferences (Authors, Years, Publishers)
            'right_query': {
                'db_type': 'MongoDB',
                'collection': 'users_profiles',
                'variables': ['user_id', 'limit'],
                'pipeline': [
                    { "$match": { "_id": "__USER_ID__" } },
                    # Split strings into arrays for matching
                    { "$addFields": {
                        "preferences.pref_authors_arr": { 
                            "$split": [{ "$ifNull": ["$preferences.pref_authors", ""] }, ","] 
                        },
                        "preferences.pref_publishers_arr": { 
                            "$split": [{ "$ifNull": ["$preferences.pref_publisher", ""] }, ","] 
                        },
                        "preferences.pref_years_arr": { 
                            "$split": [{ "$ifNull": ["$preferences.pref_pub_year", ""] }, ","] 
                        }
                    }},
                    { "$lookup": {
                        "from": "books_metadata",
                        "let": {
                            "p_sub":  { "$ifNull": ["$preferences.pref_subgenres", []] },
                            "p_authors": "$preferences.pref_authors_arr",
                            "p_publishers": "$preferences.pref_publishers_arr",
                            "p_years": "$preferences.pref_years_arr",
                            "p_avg_rating": { "$ifNull": ["$profile.mean_rating", 0] }
                        },
                        "pipeline": [
                            { "$match": {
                                "$expr": {
                                    "$and": [
                                        # A. Must match at least one specific preference (Author OR Publisher OR Year)
                                        { "$or": [
                                            { "$in": ["$extra_metadata.author", "$$p_authors"] },
                                            { "$in": ["$extra_metadata.publisher", "$$p_publishers"] },
                                            { "$in": [{ "$toString": "$extra_metadata.publication_year" }, "$$p_years"] }
                                        ]},
                                        # B. Quality Filter (Optional: keep books above user's average rating)
                                        { "$gte": ["$rating_metrics.r_avg", "$$p_avg_rating"] }
                                    ]
                                }
                            }},
                            { "$addFields": {
                                "content_score": {
                                    "$add": [
                                        { "$ifNull": ["$rating_metrics.rating_score", 0] },
                                        # Bonus: Subgenre Match (+2.0) - kept for scoring boost even if not filtering
                                        { "$cond": [
                                            { "$gt": [{ "$size": { "$setIntersection": ["$extra_metadata.subgenres", "$$p_sub"] } }, 0] },
                                            2.0, 0.0
                                        ]},
                                        # Bonus: Author Match (+3.0)
                                        { "$cond": [
                                            { "$in": ["$extra_metadata.author", "$$p_authors"] }, 
                                            3.0, 0.0
                                        ]},
                                        # Bonus: Publisher Match (+1.0)
                                        { "$cond": [
                                            { "$in": ["$extra_metadata.publisher", "$$p_publishers"] }, 
                                            1.0, 0.0
                                        ]},
                                        # Bonus: Year Match (+1.0)
                                        { "$cond": [
                                            { "$in": [{ "$toString": "$extra_metadata.publication_year" }, "$$p_years"] }, 
                                            1.0, 0.0
                                        ]},
                                        # Bonus: Popularity
                                        { "$ifNull": ["$popularity_metrics.popularity", 0] }
                                    ]
                                }
                            }},
                            { "$sort": { "content_score": -1 } },
                            { "$limit": "__LIMIT__" }
                        ],
                        "as": "recs"
                    }},
                    { "$unwind": "$recs" },
                    { "$project": {
                        "isbn": "$recs._id",
                        "content_score": "$recs.content_score",
                        "title": "$recs.title",
                        "_id": 0
                    }}
                ]
            }
        }
    }
}
# ==========================================
# PART 2: THE EXECUTOR ENGINE
# ==========================================

# ---------- MONGODB HELPER FUNCTION for pipeline parameter injection ----------
def _inject_params_into_pipeline(pipeline, params):
    """
    Deep-copy pipeline and replace string placeholders like "__LOW__" with values
    from params dict, example params = {"low": 10, "high": 50, "min_avg": 7, "limit": 5}.
    Uses a regex to extract the token between the leading/trailing double-underscores,
    so "__MIN_AVG__" -> "min_avg".
    """


    token_re = re.compile(r'^__(\w+?)__$')
    # A-Za-z0-9_ == \w
    def replace(obj):
        if isinstance(obj, dict):
            return {k: replace(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [replace(v) for v in obj]
        if isinstance(obj, str):
            m = token_re.match(obj)
            if m:
                key = m.group(1).lower()
                if key in params:
                    return params[key]
                else:
                    print(f"Warning: pipeline placeholder '{obj}' not found in params")
                    return obj
            return obj
        return obj

    return replace(copy.deepcopy(pipeline))

def execute_query(category, db_type, query_name, params=None, sql_cursor=None, mongo_db=None, mode='execution'):
    """
    Central dispatcher. Automatically returns Pandas DataFrames for data and query plans.
    """
    if params is None: params = {}
    
    # 1. Retrieve Config
    try:
        # FIX: Handle Hybrid category which has a flattened structure (no db_type layer)
        if category == 'Hybrid':
            config = QUERIES[category][query_name]
        else:
            config = QUERIES[category][db_type][query_name]
    except KeyError:
        return {"error": f"Query path '{category}/{db_type}/{query_name}' not found."}

    print(f"--- {mode.upper()}: {query_name} ({db_type}) ---")
    
    # Standard Result Payload
    payload = {
        "db_type": db_type,
        "query_name": query_name,
        "mode": mode,
        "duration_seconds": 0,
        "data": pd.DataFrame(),       # Default to empty DF
        "explain_plan": None,
        "breakdown": None
    }

    # =========================================================
    # A. HYBRID FEDERATED JOIN (The "Bridge")
    # =========================================================
    if category == "Hybrid" or config.get('type') == 'join':
        
        # 1. EXPLAIN MODE (Recursive)
        if mode == 'explain':
            left_plan = _run_sub_query(config['left_query'], params, sql_cursor, mongo_db, 'explain')
            right_plan = _run_sub_query(config['right_query'], params, sql_cursor, mongo_db, 'explain')
            
            # For Hybrid Explain, we return a dictionary of DataFrames/Dicts
            payload['explain_plan'] = {
                "Left_MySQL": left_plan.get('explain_plan'),
                "Right_Mongo": right_plan.get('explain_plan'),
                "Strategy": pd.DataFrame([{
                    "Join_Type": config['how'].upper(),
                    "Keys": str(config['join_keys']),
                    "Logic": "Pandas Application-Side Merge"
                }])
            }
            return payload

        # 2. EXECUTION MODE (Recursive + Merge)
        else:
            total_start = time.time()
            
            # Fetch Left (MySQL) -> Returns Dict with DataFrame inside
            left_res = _run_sub_query(config['left_query'], params, sql_cursor, mongo_db, 'execution')
            df_left = left_res['data']
            
            # Fetch Right (Mongo) -> Returns Dict with DataFrame inside
            right_res = _run_sub_query(config['right_query'], params, sql_cursor, mongo_db, 'execution')
            df_right = right_res['data']
            
            # Perform Application-Side Join
            if not df_left.empty and not df_right.empty:
                df_joined = pd.merge(
                    df_left, df_right, 
                    left_on=config['join_keys']['left'], 
                    right_on=config['join_keys']['right'], 
                    how=config['how']
                )
                payload['data'] = df_joined
            
            total_end = time.time()
            payload['duration_seconds'] = total_end - total_start
            
            # Detailed timing breakdown
            payload['breakdown'] = {
                "MySQL_Fetch": left_res['duration_seconds'],
                "MongoDB_Fetch": right_res['duration_seconds'],
                "Pandas_Merge": (total_end - total_start) - (left_res['duration_seconds'] + right_res['duration_seconds'])
            }
            return payload

    # =========================================================
    # B. SINGLE DB EXECUTION
    # =========================================================
    
    # NOTE: The 'Simple' and 'Complex' configs don't have 'db_type' inside them, 
    # it's inferred from the parent key. We must inject it for _run_sub_query to work.
    if 'db_type' not in config:
        config = config.copy()
        config['db_type'] = db_type

    return _run_sub_query(config, params, sql_cursor, mongo_db, mode)


def _run_sub_query(config, params, sql_cursor, mongo_db, mode):
    """
    Helper function. Handles DB drivers and forces Pandas conversion.
    Supports:
      - MySQL: single query string in config['query']
      - MongoDB: single or multiple collections with handled within the
      same pipeline logic, always of aggregate type, even though it works for find
      as well. 
    """
    res = {"explain_plan": None, "data": pd.DataFrame(), "duration_seconds": 0}
    db_type = config.get('db_type', 'Unknown')

    # --- MYSQL LOGIC ---
    if db_type == 'MySQL':
        sql = config['query']
        try:
            if mode == 'explain':
                # Explain returns a table, so we convert it to DataFrame immediately
                sql_cursor.execute(f"EXPLAIN {sql}", params)
                res['explain_plan'] = pd.DataFrame(sql_cursor.fetchall())
            else:
                t0 = time.time()
                sql_cursor.execute(sql, params)
                # Convert list of dicts directly to DataFrame
                res['data'] = pd.DataFrame(sql_cursor.fetchall())
                res['duration_seconds'] = time.time() - t0
        except Exception as e:
            print(f"MySQL Error: {e}")
        return res

    # --- MONGODB LOGIC (supports multiple collections) ---
    elif db_type == 'MongoDB':
        # Determine target collections (support 'collection' or 'collections')
        collections = []
        if 'collections' in config and isinstance(config['collections'], (list, tuple)):
            collections = list(config['collections'])
        elif 'collection' in config and isinstance(config['collection'], str):
            collections = [config['collection']]
        else:
            # nothing to run
            return res

        explain_dict = {}
        dfs = []
        total_time = 0.0

        for coll_name in collections:
            # Decide pipeline for this collection
            pipeline = config.get('pipeline', [])
            pipelines_cfg = config.get('pipelines')
            if isinstance(pipelines_cfg, dict):
                pipeline = pipelines_cfg.get(coll_name, pipeline)

            # Inject params (safer structured replacement)
            pipeline_local = _inject_params_into_pipeline(pipeline, params) if params else pipeline

            coll = mongo_db[coll_name]

            try:
                if mode == 'explain':
                    if config.get('type') == 'find':
                        explain_dict[coll_name] = coll.find(pipeline_local[0]).explain()
                    elif config.get('type') == 'aggregate':
                        explain_dict[coll_name] = mongo_db.command(
                            'aggregate', coll_name, pipeline=pipeline_local, explain=True
                        )
                else:
                    t0 = time.time()
                    data_list = []
                    if config.get('type') == 'aggregate':
                        data_list = list(coll.aggregate(pipeline_local))
                    elif config.get('type') == 'find':
                        # pipeline_local[0] expected to be a filter dict for find
                        data_list = list(coll.find(pipeline_local[0] if isinstance(pipeline_local, list) and pipeline_local else pipeline_local))
                    dt = time.time() - t0
                    total_time += dt

                    if data_list:
                        dfs.append(pd.DataFrame(data_list))
            except Exception as e:
                print(f"Mongo Error on collection '{coll_name}': {e}")

        # Compose results
        if mode == 'explain':
            res['explain_plan'] = explain_dict
        else:
            if dfs:
                # Concatenate results from all collections into a single DataFrame
                res['data'] = pd.concat(dfs, ignore_index=True, sort=False)
            res['duration_seconds'] = total_time

        return res

    return res