Here is the updated, optimal code.

**Key Change:** The `execute_query` function now automatically converts results into **Pandas DataFrames**. You no longer need to write `pd.DataFrame(...)` in your Notebook cells.

### File 1: [`query_helper.py`](query_helper.py)


### File 2: [`Report_Analysis.ipynb`](../notebooks/4_recommendation_queries.ipynb) (Jupyter Notebook)

Notice how clean the notebook cells are now. `pd.DataFrame()` is gone.

#### Cell 1: Setup

- Connect to MongoDB an MySQL

#### Cell 2: Simple Queries

```python
# --- MySQL Run ---
mysql_res = query_helper.execute_query(
    'Simple', 'MySQL', 'top_books', 
    params={'limit': 5}, 
    sql_cursor=sql_cursor, mode='execution'
)
print(f"Duration: {mysql_res['duration_seconds']:.4f}s")

# Result is ALREADY a DataFrame. Just display it.
display(mysql_res['data'])

# --- MongoDB Run ---
mongo_res = query_helper.execute_query(
    'Simple', 'MongoDB', 'price_range', 
    params={'VAR_LOW': 10, 'VAR_HIGH': 50, 'VAR_LIMIT': 5}, 
    mongo_db=mongo_db, mode='execution'
)
print(f"Duration: {mongo_res['duration_seconds']:.4f}s")
display(mongo_res['data'])
```

#### Cell 3: Hybrid Execution

```python
# --- Hybrid Join Execution ---
hybrid_perf = query_helper.execute_query(
    'Hybrid', 'Combined', 'enriched_books',
    params={'limit': 100, 'VAR_MAX_PRICE': 25},
    sql_cursor=sql_cursor, mongo_db=mongo_db,
    mode='execution'
)

print(f"Total Time: {hybrid_perf['duration_seconds']:.4f}s")
print("Breakdown:", hybrid_perf['breakdown'])

# Display Joined Data
display(hybrid_perf['data'].head())
```

#### Cell 4: Hybrid Explain (Structure)

```python
# --- Hybrid Explain ---
hybrid_explain = query_helper.execute_query(
    'Hybrid', 'Combined', 'enriched_books',
    params={'limit': 100, 'VAR_MAX_PRICE': 25},
    sql_cursor=sql_cursor, mongo_db=mongo_db,
    mode='explain'
)

# Display MySQL Plan
print("--- MySQL Plan ---")
display(hybrid_explain['explain_plan']['Left_MySQL'])

# Display Join Strategy
print("--- Join Strategy ---")
display(hybrid_explain['explain_plan']['Strategy'])
```