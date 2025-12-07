"""
User Taste Evolution Analyzer
Analyzes how a user's reading preferences have changed over time.
Uses r_seq_user to track chronological progression.
"""

from sqlalchemy import text
from collections import Counter, defaultdict


def get_user_reading_timeline(mysql_engine, user_id):
    """Get user's reading history ordered by sequence"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT r.isbn, r.rating, r.r_seq_user, r.r_cat, b.authors
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            WHERE r.user_id = :user_id
            ORDER BY r.r_seq_user ASC
        """), {"user_id": user_id})
        
        timeline = []
        for row in result.fetchall():
            timeline.append({
                "isbn": row[0],
                "rating": row[1],
                "sequence": row[2],
                "category": row[3],
                "authors": row[4]
            })
        
        return timeline


def analyze_genre_evolution(mysql_engine, user_id, num_periods=4):
    """Analyze how genre preferences changed over time"""
    with mysql_engine.connect() as conn:
        # Get all ratings with genres, ordered by sequence
        result = conn.execute(text("""
            SELECT r.r_seq_user, rg.genre_name
            FROM ratings r
            JOIN books b ON r.isbn = b.isbn
            JOIN books_subgenres bs ON b.isbn = bs.isbn
            JOIN subgenres sg ON bs.subgenre_id = sg.subgenre_id
            JOIN root_genres rg ON sg.root_genre_id = rg.root_genre_id
            WHERE r.user_id = :user_id
            ORDER BY r.r_seq_user ASC
        """), {"user_id": user_id})
        
        all_data = [(row[0], row[1]) for row in result.fetchall()]
        
        if not all_data:
            return []
        
        # Split into periods
        total = len(all_data)
        period_size = total // num_periods
        
        periods = []
        for i in range(num_periods):
            start_idx = i * period_size
            end_idx = start_idx + period_size if i < num_periods - 1 else total
            
            period_data = all_data[start_idx:end_idx]
            genre_counts = Counter([genre for _, genre in period_data])
            
            periods.append({
                "period": i + 1,
                "start_seq": period_data[0][0],
                "end_seq": period_data[-1][0],
                "book_count": len(period_data),
                "top_genres": genre_counts.most_common(5)
            })
        
        return periods


def analyze_rating_evolution(timeline, num_periods=4):
    """Analyze how rating behavior changed over time"""
    if not timeline:
        return []
    
    total = len(timeline)
    period_size = total // num_periods
    
    periods = []
    for i in range(num_periods):
        start_idx = i * period_size
        end_idx = start_idx + period_size if i < num_periods - 1 else total
        
        period_data = timeline[start_idx:end_idx]
        ratings = [item["rating"] for item in period_data]
        
        periods.append({
            "period": i + 1,
            "avg_rating": sum(ratings) / len(ratings),
            "min_rating": min(ratings),
            "max_rating": max(ratings),
            "rating_range": max(ratings) - min(ratings),
            "book_count": len(period_data)
        })
    
    return periods


def analyze_author_diversity(timeline, num_periods=4):
    """Analyze author diversity over time"""
    if not timeline:
        return []
    
    total = len(timeline)
    period_size = total // num_periods
    
    periods = []
    for i in range(num_periods):
        start_idx = i * period_size
        end_idx = start_idx + period_size if i < num_periods - 1 else total
        
        period_data = timeline[start_idx:end_idx]
        
        all_authors = []
        for item in period_data:
            authors_str = item["authors"]
            if authors_str:
                authors = [a.strip().strip("'\"[]") for a in authors_str.split(",")]
                all_authors.extend(authors)
        
        unique_authors = len(set(all_authors))
        total_books = len(period_data)
        diversity_ratio = unique_authors / total_books if total_books > 0 else 0
        
        periods.append({
            "period": i + 1,
            "unique_authors": unique_authors,
            "total_books": total_books,
            "diversity_ratio": diversity_ratio
        })
    
    return periods


def analyze_price_sensitivity(mysql_engine, mongo_db, user_id, num_periods=4):
    """Analyze price preference evolution"""
    with mysql_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT r.r_seq_user, r.isbn
            FROM ratings r
            WHERE r.user_id = :user_id
            ORDER BY r.r_seq_user ASC
        """), {"user_id": user_id})
        
        seq_isbn_pairs = [(row[0], row[1]) for row in result.fetchall()]
    
    if not seq_isbn_pairs:
        return []
    
    # Get prices from MongoDB
    seq_prices = []
    for seq, isbn in seq_isbn_pairs:
        book_meta = mongo_db.books_metadata.find_one({"_id": isbn})
        if book_meta and "price" in book_meta:
            price = book_meta["price"]
            if price:
                seq_prices.append((seq, price))
    
    if not seq_prices:
        return []
    
    # Split into periods
    total = len(seq_prices)
    period_size = total // num_periods
    
    periods = []
    for i in range(num_periods):
        start_idx = i * period_size
        end_idx = start_idx + period_size if i < num_periods - 1 else total
        
        period_data = seq_prices[start_idx:end_idx]
        prices = [price for _, price in period_data]
        
        periods.append({
            "period": i + 1,
            "avg_price": sum(prices) / len(prices),
            "min_price": min(prices),
            "max_price": max(prices),
            "book_count": len(prices)
        })
    
    return periods


def identify_taste_changes(genre_periods):
    """Identify significant taste changes"""
    changes = []
    
    for i in range(len(genre_periods) - 1):
        current = dict(genre_periods[i]["top_genres"])
        next_period = dict(genre_periods[i + 1]["top_genres"])
        
        # Find new emerging genres
        new_genres = set(next_period.keys()) - set(current.keys())
        if new_genres:
            for genre in new_genres:
                changes.append({
                    "period_transition": f"{i + 1} → {i + 2}",
                    "type": "new_interest",
                    "genre": genre,
                    "count": next_period[genre]
                })
        
        # Find declining genres
        declining_genres = set(current.keys()) - set(next_period.keys())
        if declining_genres:
            for genre in declining_genres:
                changes.append({
                    "period_transition": f"{i + 1} → {i + 2}",
                    "type": "declining_interest",
                    "genre": genre,
                    "count": current[genre]
                })
    
    return changes


def display_evolution_analysis(user_id, timeline, genre_periods, rating_periods, author_periods, price_periods, changes):
    """Display taste evolution analysis"""
    print("\n" + "=" * 80)
    print("📈 USER TASTE EVOLUTION ANALYSIS")
    print("=" * 80)
    
    print(f"\nUser ID: {user_id}")
    print(f"Total Books Rated: {len(timeline)}")
    if timeline:
        print(f"Reading Sequence: {timeline[0]['sequence']} → {timeline[-1]['sequence']}")
    
    # Genre Evolution
    print("\n" + "=" * 80)
    print("📚 GENRE PREFERENCES OVER TIME")
    print("=" * 80)
    
    for period in genre_periods:
        print(f"\nPeriod {period['period']} ({period['book_count']} books):")
        print(f"  Top Genres:")
        for genre, count in period['top_genres'][:3]:
            pct = (count / period['book_count']) * 100
            print(f"    • {genre}: {count} books ({pct:.1f}%)")
    
    # Rating Behavior Evolution
    print("\n" + "=" * 80)
    print("⭐ RATING BEHAVIOR OVER TIME")
    print("=" * 80)
    
    for period in rating_periods:
        print(f"\nPeriod {period['period']}:")
        print(f"  Average Rating: {period['avg_rating']:.2f}/10")
        print(f"  Rating Range: {period['min_rating']}-{period['max_rating']} (spread: {period['rating_range']})")
    
    # Determine if user became harsher or more generous
    if len(rating_periods) >= 2:
        first_avg = rating_periods[0]['avg_rating']
        last_avg = rating_periods[-1]['avg_rating']
        diff = last_avg - first_avg
        
        if abs(diff) > 0.5:
            trend = "more generous" if diff > 0 else "harsher"
            print(f"\n  Trend: You've become {trend} over time ({diff:+.2f} change)")
    
    # Author Diversity
    print("\n" + "=" * 80)
    print("👥 AUTHOR EXPLORATION")
    print("=" * 80)
    
    for period in author_periods:
        print(f"\nPeriod {period['period']}:")
        print(f"  Unique Authors: {period['unique_authors']}")
        print(f"  Diversity Ratio: {period['diversity_ratio']:.2f} (authors per book)")
    
    if len(author_periods) >= 2:
        first_ratio = author_periods[0]['diversity_ratio']
        last_ratio = author_periods[-1]['diversity_ratio']
        
        if last_ratio > first_ratio * 1.2:
            print("\n  Trend: You're exploring more diverse authors")
        elif last_ratio < first_ratio * 0.8:
            print("\n  Trend: You're focusing on fewer favorite authors")
    
    # Price Sensitivity
    if price_periods:
        print("\n" + "=" * 80)
        print("💰 PRICE PREFERENCES")
        print("=" * 80)
        
        for period in price_periods:
            print(f"\nPeriod {period['period']}:")
            print(f"  Average Price: ${period['avg_price']:.2f}")
            print(f"  Price Range: ${period['min_price']:.2f} - ${period['max_price']:.2f}")
        
        if len(price_periods) >= 2:
            first_avg = price_periods[0]['avg_price']
            last_avg = price_periods[-1]['avg_price']
            diff = last_avg - first_avg
            
            if abs(diff) > 3:
                trend = "more expensive" if diff > 0 else "less expensive"
                print(f"\n  Trend: You're reading {trend} books (${diff:+.2f} change)")
    
    # Significant Changes
    if changes:
        print("\n" + "=" * 80)
        print("🔄 SIGNIFICANT TASTE CHANGES")
        print("=" * 80)
        
        new_interests = [c for c in changes if c["type"] == "new_interest"]
        if new_interests:
            print("\n  New Genre Interests:")
            for change in new_interests[:5]:
                print(f"    • {change['genre']} (appeared in {change['period_transition']})")


def analyze_taste_evolution(mysql_engine, mongo_db, user_id, periods=4):
    """Analyze user taste evolution"""
    
    # Get timeline
    timeline = get_user_reading_timeline(mysql_engine, user_id)
    
    if not timeline:
        return None
    
    # Analyze different dimensions
    genre_periods = analyze_genre_evolution(mysql_engine, user_id, periods)
    rating_periods = analyze_rating_evolution(timeline, periods)
    author_periods = analyze_author_diversity(timeline, periods)
    price_periods = analyze_price_sensitivity(mysql_engine, mongo_db, user_id, periods)
    changes = identify_taste_changes(genre_periods)
    
    return {
        "timeline": timeline,
        "genre_periods": genre_periods,
        "rating_periods": rating_periods,
        "author_periods": author_periods,
        "price_periods": price_periods,
        "changes": changes
    }
