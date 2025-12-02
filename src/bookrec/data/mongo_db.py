from __future__ import annotations

from typing import Any

from pymongo import MongoClient, ASCENDING, DESCENDING, GEOSPHERE
from pymongo.database import Database

from bookrec.config import get_settings


_client: MongoClient | None = None
_db: Database | None = None


def get_mongo_client() -> MongoClient:
    """Get MongoDB client (singleton)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = MongoClient(settings.mongo_uri)
    return _client


def get_mongo_db() -> Database:
    """Get MongoDB database handle."""
    global _db
    if _db is None:
        settings = get_settings()
        client = get_mongo_client()
        _db = client[settings.mongo_database]
    return _db


def init_mongo_collections() -> None:
    """Create MongoDB collections and indexes (idempotent).
    
    Collections:
    - user_profiles: user preferences, reading history, tags
    - book_details: extended metadata, reviews, categories (nested)
    - interaction_logs: user-item interaction events (clicks, views, searches)
    - recommendation_cache: pre-computed recommendations
    """
    db = get_mongo_db()
    
    # user_profiles: flexible user data (preferences, history)
    if "user_profiles" not in db.list_collection_names():
        db.create_collection("user_profiles")
    db.user_profiles.create_index([("user_id", ASCENDING)], unique=True)
    # Spatial index for geographic queries (GeoJSON Point stored at location.coordinates)
    try:
        db.user_profiles.create_index([("location.coordinates", GEOSPHERE)], name="geo_location_index")
    except Exception:
        # If index creation fails (e.g., older server), continue without crashing; log externally if needed
        pass
    
    # book_details: nested book metadata beyond core fields
    if "book_details" not in db.list_collection_names():
        db.create_collection("book_details")
    db.book_details.create_index([("isbn", ASCENDING)], unique=True)
    db.book_details.create_index([("categories", ASCENDING)])
    
    # interaction_logs: event stream (clicks, views, searches)
    if "interaction_logs" not in db.list_collection_names():
        db.create_collection("interaction_logs")
    db.interaction_logs.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)])
    db.interaction_logs.create_index([("isbn", ASCENDING)])
    # TTL index for interaction logs (optional): expire after 180 days
    try:
        db.interaction_logs.create_index([("timestamp", ASCENDING)], expireAfterSeconds=60 * 60 * 24 * 180, name="ttl_interaction_logs")
    except Exception:
        # Not all collection/indexing setups allow TTL; ignore if unsupported
        pass
    
    # recommendation_cache: pre-computed recs for users
    if "recommendation_cache" not in db.list_collection_names():
        db.create_collection("recommendation_cache")
    db.recommendation_cache.create_index([("user_id", ASCENDING)], unique=True)


def drop_mongo_collections() -> None:
    """Drop all MongoDB collections (for testing/reset)."""
    db = get_mongo_db()
    for coll in ["user_profiles", "book_details", "interaction_logs", "recommendation_cache"]:
        if coll in db.list_collection_names():
            db.drop_collection(coll)
