# MongoDB Schema Documentation

## Overview
MongoDB stores denormalized metadata and computed metrics that complement the relational MySQL schema. The document-based structure handles sparse data efficiently and supports flexible querying for recommendation features.

**Database Name:** `bookrec`

---

## Collections

### 1. `books_metadata`

Stores extended book information including images, descriptions, pricing, and computed rating/popularity metrics.

**Primary Key:** `_id` (ISBN)

#### Document Structure

```javascript
{
  "_id": "0195153448",  // ISBN (string)
  
  "extra_metadata": {
    "price_usd": 29.95,                    // Decimal, nullable
    "genre": "Fiction",                     // String, nullable
    "root_genres": ["Fiction", "Mystery"],  // Array of strings
    "subgenres": ["Thriller", "Crime"],     // Array of strings
    "regional_tags": ["European"],          // Array of strings, nullable
    "image_alternative": "...",             // String URL, nullable
    "previewlink": "https://...",           // String URL, nullable
    "infolink": "https://...",              // String URL, nullable
    "image_url_s": "https://...",           // Small image URL
    "image_url_m": "https://...",           // Medium image URL
    "image_url_l": "https://...",           // Large image URL
    "description": "Long text..."           // Text, nullable
  },
  
  "rating_metrics": {
    "rating_score": 8.5,          // Computed rating score
    "r_category": "highly_rated",  // Rating category
    "r_total": 1250,              // Total rating sum
    "r_count": 150,               // Number of ratings
    "r_avg": 8.33,                // Average rating
    "r_std": 1.2                  // Standard deviation
  },
  
  "popularity_metrics": {
    "recent_count": 45,           // Recent ratings count
    "popularity": 0.85,           // Normalized popularity score
    "popularity_cat": "popular"   // Category: popular/trending/niche
  }
}
```

#### Field Definitions

**extra_metadata:**
- `price_usd`: Book price in USD (sparse field)
- `genre`: Primary genre classification
- `root_genres`: Top-level genre categories (array)
- `subgenres`: Specific genre classifications (array)
- `regional_tags`: Geographic/cultural tags
- `image_alternative`: Alternative image URL
- `previewlink`: Preview link (e.g., Google Books)
- `infolink`: Information link (e.g., Google Books)
- `image_url_s/m/l`: Image URLs in small/medium/large sizes
- `description`: Full book description/synopsis

**rating_metrics:**
- `rating_score`: Computed composite rating score
- `r_category`: Categorical rating level
- `r_total`: Sum of all ratings received
- `r_count`: Total number of ratings
- `r_avg`: Mean rating value
- `r_std`: Rating standard deviation (consistency measure)

**popularity_metrics:**
- `recent_count`: Count of recent ratings (time-windowed)
- `popularity`: Normalized popularity score (0-1)
- `popularity_cat`: Categorical popularity classification

---

### 2. `users_profiles`

Stores user reading behavior profiles, preferences, and computed statistics for personalization.

**Primary Key:** `_id` (user_id)

#### Document Structure

```javascript
{
  "_id": 12345,  // user_id (integer)
  
  "profile": {
    "reader_level": "active",        // casual/active/power/critic
    "critic_profile": "harsh",       // lenient/moderate/harsh
    "mean_rating": 7.5,              // Average rating given
    "median_rating": 8.0,            // Median rating given
    "std_rating": 1.8,               // Rating standard deviation
    "total_ratings": 150,            // Total ratings count
    "total_books": 145,              // Unique books rated
    "explicit_ratings": 120,         // Non-implicit ratings count
    "has_ratings": true,             // Boolean flag
    "has_preferences": true          // Boolean flag
  },
  
  "preferences": {
    "pref_pub_year": 2015,           // Preferred publication year
    "pref_root_genres": [            // Preferred root genres (array)
      "Fiction",
      "Science Fiction"
    ],
    "pref_subgenres": [              // Preferred subgenres (array)
      "Space Opera",
      "Cyberpunk"
    ],
    "pref_authors": [                // Preferred authors (array)
      "Isaac Asimov",
      "Arthur C. Clarke"
    ],
    "pref_publisher": "Tor Books",   // Preferred publisher
    "pref_price_min": 9.99,          // Minimum price preference
    "pref_price_max": 29.99,         // Maximum price preference
    "pref_price_avg": 19.99          // Average price preference
  }
}
```

#### Field Definitions

**profile:**
- `reader_level`: User engagement level classification
  - `casual`: Infrequent reader
  - `active`: Regular reader
  - `power`: Heavy reader
  - `critic`: Very active with detailed ratings
- `critic_profile`: Rating behavior pattern
  - `lenient`: Tends to rate high
  - `moderate`: Balanced ratings
  - `harsh`: Tends to rate low
- `mean_rating`: User's average rating score
- `median_rating`: User's median rating score
- `std_rating`: Variability in user's ratings
- `total_ratings`: Total number of ratings submitted
- `total_books`: Count of unique books rated
- `explicit_ratings`: Non-implicit/direct ratings
- `has_ratings`: Flag indicating if user has any ratings
- `has_preferences`: Flag indicating if preferences computed

**preferences:**
- `pref_pub_year`: Most frequently rated publication year
- `pref_root_genres`: Top-level genres user prefers (array)
- `pref_subgenres`: Specific genres user prefers (array)
- `pref_authors`: Frequently rated authors (array)
- `pref_publisher`: Most common publisher in user's ratings
- `pref_price_min`: Lower bound of price range user rates
- `pref_price_max`: Upper bound of price range user rates
- `pref_price_avg`: Average price of books user rates

---

## Indexing Strategy

### Recommended Indexes

**books_metadata:**
```javascript
// Primary key index (automatic)
db.books_metadata.createIndex({ "_id": 1 })

// Genre-based queries
db.books_metadata.createIndex({ "extra_metadata.root_genres": 1 })
db.books_metadata.createIndex({ "extra_metadata.subgenres": 1 })

// Rating-based filtering
db.books_metadata.createIndex({ "rating_metrics.r_category": 1 })
db.books_metadata.createIndex({ "rating_metrics.r_avg": -1 })

// Popularity-based queries
db.books_metadata.createIndex({ "popularity_metrics.popularity_cat": 1 })
db.books_metadata.createIndex({ "popularity_metrics.popularity": -1 })

// Price range queries
db.books_metadata.createIndex({ "extra_metadata.price_usd": 1 })

// Compound index for recommendation queries
db.books_metadata.createIndex({ 
  "extra_metadata.root_genres": 1,
  "rating_metrics.r_avg": -1,
  "popularity_metrics.popularity": -1
})
```

**users_profiles:**
```javascript
// Primary key index (automatic)
db.users_profiles.createIndex({ "_id": 1 })

// User segmentation queries
db.users_profiles.createIndex({ "profile.reader_level": 1 })
db.users_profiles.createIndex({ "profile.critic_profile": 1 })

// Preference-based matching
db.users_profiles.createIndex({ "preferences.pref_root_genres": 1 })
db.users_profiles.createIndex({ "preferences.pref_subgenres": 1 })
db.users_profiles.createIndex({ "preferences.pref_authors": 1 })

// User activity filtering
db.users_profiles.createIndex({ "profile.has_preferences": 1 })
db.users_profiles.createIndex({ "profile.total_ratings": -1 })
```

---

## Data Types Summary

| Field Type | MongoDB Type | Example |
|------------|--------------|---------|
| ISBN | String | "0195153448" |
| user_id | Integer | 12345 |
| Prices | Decimal/Number | 29.95 |
| Counts | Integer | 150 |
| Scores | Number (float) | 8.5 |
| Categories | String | "highly_rated" |
| Arrays | Array | ["Fiction", "Mystery"] |
| Flags | Boolean | true/false |
| Text | String | "Long description..." |

---

## Query Examples

### Find highly-rated fiction books
```javascript
db.books_metadata.find({
  "extra_metadata.root_genres": "Fiction",
  "rating_metrics.r_category": "highly_rated",
  "popularity_metrics.popularity": { $gte: 0.7 }
}).sort({ "rating_metrics.r_avg": -1 }).limit(10)
```

### Find active users who prefer sci-fi
```javascript
db.users_profiles.find({
  "profile.reader_level": "active",
  "preferences.pref_root_genres": "Science Fiction",
  "profile.has_preferences": true
})
```

### Find books in price range with good ratings
```javascript
db.books_metadata.find({
  "extra_metadata.price_usd": { $gte: 10, $lte: 30 },
  "rating_metrics.r_avg": { $gte: 7.0 },
  "rating_metrics.r_count": { $gte: 20 }
})
```

---

## Notes

- **Sparse Fields**: Many fields in `extra_metadata` are nullable/optional, leveraging MongoDB's flexible schema
- **Array Fields**: Genre and preference arrays support multi-valued attributes efficiently
- **Computed Metrics**: Rating and popularity metrics are pre-computed for fast queries
- **Denormalization**: Data is denormalized from MySQL for read optimization
- **Foreign Keys**: `_id` fields correspond to primary keys in MySQL (`isbn`, `user_id`)
