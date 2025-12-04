# Book Recommendation Scripts

This folder contains all recommendation query scripts for the hybrid MySQL+MongoDB book recommendation system.

## 📁 Organization

All recommendation scripts are organized by type:

### Core Recommendation Engines
1. **recommendation_content_based.py** - Content-based filtering using genres, authors, and price preferences
2. **recommendation_collaborative.py** - Collaborative filtering based on similar users
3. **recommendation_hybrid.py** - Weighted combination of multiple strategies
4. **recommendation_trending.py** - Trending books with recent activity and momentum

### Specialized Recommendations
5. **recommendation_geographic.py** - Region-based recommendations using location clustering
6. **recommendation_cold_start.py** - Recommendations for new users based on demographics
7. **recommendation_diverse.py** - Diversity-aware recommendations across genres/authors
8. **recommendation_similar_books.py** - Find books similar to a given book

### Query Utilities
9. **query_compatibility_score.py** - Calculate user-book compatibility metrics
10. **query_recommendation_explanation.py** - Generate human-readable recommendation explanations
11. **query_taste_evolution.py** - Analyze how user preferences changed over time
12. **query_recommendation_dashboard.py** - Comprehensive multi-strategy recommendation report

## 🚀 Usage Examples

### Content-Based Recommendations
```bash
python recommendations/recommendation_content_based.py --user_id 12345 --limit 10
```

### Collaborative Filtering
```bash
python recommendations/recommendation_collaborative.py --user_id 12345 --min_common 5
```

### Hybrid Recommendations (Configurable Weights)
```bash
python recommendations/recommendation_hybrid.py --user_id 12345 \
  --content_weight 0.5 --collab_weight 0.3 --popularity_weight 0.2
```

### Geographic Recommendations
```bash
python recommendations/recommendation_geographic.py --user_id 12345 --radius 100
```

### Cold-Start for New Users
```bash
python recommendations/recommendation_cold_start.py --user_id 67890
```

### Diversity-Aware Recommendations
```bash
python recommendations/recommendation_diverse.py --user_id 12345 \
  --diversity 0.7 --max_per_author 2
```

### Trending Books
```bash
python recommendations/recommendation_trending.py --user_id 12345 \
  --recent_window 10 --min_ratings 10
```

### Similar Books
```bash
python recommendations/recommendation_similar_books.py --isbn "0439136350"
```

### Compatibility Score
```bash
python recommendations/query_compatibility_score.py --user_id 12345 --isbn "0439136350"
```

### Recommendation Explanation
```bash
python recommendations/query_recommendation_explanation.py --user_id 12345 --isbn "0439136350"
```

### Taste Evolution Analysis
```bash
python recommendations/query_taste_evolution.py --user_id 12345 --periods 4
```

### Comprehensive Dashboard
```bash
python recommendations/query_recommendation_dashboard.py --user_id 12345 --per_category 5
```

## 🔧 Common Parameters

- `--user_id` (int): Target user ID (required for most scripts)
- `--isbn` (str): Target book ISBN (for similarity and compatibility)
- `--limit` (int): Number of recommendations to return (default: 10-20)
- `--min_rating` (int): Minimum rating threshold (default: 7)

## 🎯 Recommendation Strategy Guide

### When to Use Each Script

**Content-Based**: User has established preferences, want genre/author matching
**Collaborative**: User has many ratings, leverage community wisdom  
**Hybrid**: Best overall performance, combines multiple signals  
**Trending**: Show what's hot right now, time-sensitive recommendations  
**Geographic**: Leverage regional reading patterns  
**Cold-Start**: New users with few/no ratings  
**Diverse**: Avoid filter bubbles, encourage exploration  
**Similar Books**: "More like this" functionality  

### Metrics Explained

- **Quality Score**: Bayesian average rating (0-10)
- **Velocity Score**: Recent activity × quality
- **Similarity Score**: Genre + author + metadata matching
- **Compatibility Score**: Multi-factor user-book alignment

## 🗄️ Database Dependencies

All scripts require:
- MySQL connection with `users`, `books`, `ratings`, genre tables
- MongoDB connection with `books_metadata` and `users_profiles` collections
- `.env` file with database credentials in project root

## 📊 Performance Notes

- Scripts use connection pooling for efficiency
- Geographic queries use Haversine distance calculation
- Collaborative filtering limited to 500 candidate users for performance
- Hybrid recommendations process up to 1000 candidate books

## 🔍 Troubleshooting

**No recommendations returned**: User may have insufficient data or unique tastes  
**Slow performance**: Reduce limit, add database indexes, use caching  
**Geographic not working**: User location data may be missing  
**Cold-start issues**: Need more demographic data or global fallbacks  

## 📚 Related Documentation

See `../queries.md` for detailed query explanations and algorithm descriptions.
