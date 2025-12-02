"""
Geographic transformation utilities for book recommendation system.

This module provides functions to transform user location strings into
precise latitude/longitude coordinates for spatial indexing and 
geographic collaborative filtering.

Author: Book Rec Team
Date: November 2025
"""

import time
import logging
from typing import Optional, Tuple, Dict, Any
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
import re

# Configure logging
logger = logging.getLogger(__name__)

class GeographicTransformer:
    """
    Handles transformation of location strings to geographic coordinates.
    
    Features:
    - Robust error handling for failed geocoding
    - Rate limiting to respect geocoding service limits
    - Caching to avoid duplicate API calls
    - Data cleaning for common location string formats
    """
    
    def __init__(self, user_agent: str = "bookrec_geocoder", 
                 rate_limit_delay: float = 1.0):
        """
        Initialize the geographic transformer.
        
        Args:
            user_agent: Identifier for the geocoding service
            rate_limit_delay: Delay between geocoding requests (seconds)
        """
        self.geolocator = Nominatim(
            user_agent=user_agent,
            timeout=10
        )
        self.rate_limit_delay = rate_limit_delay
        self.cache = {}  # Simple in-memory cache
        self.failed_locations = set()  # Track failed geocoding attempts
        
    def clean_location_string(self, location: str) -> str:
        """
        Clean and standardize location strings for better geocoding success.
        
        Args:
            location: Raw location string (e.g., "nyc, new york, usa")
            
        Returns:
            Cleaned location string
        """
        if not location or location.strip() == "":
            return ""
            
        # Convert to lowercase and strip whitespace
        cleaned = location.lower().strip()
        
        # Remove extra whitespace and normalize separators
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = re.sub(r',\s*,', ',', cleaned)  # Remove empty components
        
        # Common abbreviation expansions
        replacements = {
            r'\bnyc\b': 'new york city',
            r'\bla\b': 'los angeles',
            r'\bsf\b': 'san francisco',
            r'\bdc\b': 'washington dc',
            r'\buk\b': 'united kingdom',
            r'\busa\b': 'united states',
            r'\bus\b': 'united states',
            r'\bca\b(?=\s*$|,)': 'california',  # Only at end or before comma
        }
        
        for pattern, replacement in replacements.items():
            cleaned = re.sub(pattern, replacement, cleaned)
            
        return cleaned
        
    def geocode_location(self, location: str) -> Optional[Dict[str, Any]]:
        """
        Transform location string to geographic coordinates.
        
        Args:
            location: Location string to geocode
            
        Returns:
            Dictionary with coordinates and metadata, or None if failed
            Format: {
                'coordinates': [longitude, latitude],  # GeoJSON format
                'display_name': str,
                'country': str,
                'confidence': float
            }
        """
        if not location or location.strip() == "":
            return None
            
        # Clean the location string
        cleaned_location = self.clean_location_string(location)
        
        # Check cache first
        if cleaned_location in self.cache:
            logger.debug(f"Cache hit for location: {cleaned_location}")
            return self.cache[cleaned_location]
            
        # Skip if we've already failed to geocode this location
        if cleaned_location in self.failed_locations:
            logger.debug(f"Skipping previously failed location: {cleaned_location}")
            return None
            
        try:
            # Rate limiting
            time.sleep(self.rate_limit_delay)
            
            # Attempt geocoding
            logger.debug(f"Geocoding location: {cleaned_location}")
            result = self.geolocator.geocode(
                cleaned_location,
                exactly_one=True,
                addressdetails=True
            )
            
            if result:
                # Extract country from address components
                country = "unknown"
                if hasattr(result, 'raw') and 'address' in result.raw:
                    address = result.raw['address']
                    country = address.get('country', 'unknown')
                
                # Create standardized result
                geo_data = {
                    'coordinates': [result.longitude, result.latitude],  # GeoJSON format [lng, lat]
                    'display_name': result.address,
                    'country': country,
                    'confidence': getattr(result, 'confidence', 1.0),
                    'original_location': location
                }
                
                # Cache the successful result
                self.cache[cleaned_location] = geo_data
                logger.info(f"Successfully geocoded: {cleaned_location} -> {geo_data['coordinates']}")
                return geo_data
                
            else:
                logger.warning(f"No results found for location: {cleaned_location}")
                self.failed_locations.add(cleaned_location)
                return None
                
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            logger.error(f"Geocoding service error for '{cleaned_location}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error geocoding '{cleaned_location}': {e}")
            self.failed_locations.add(cleaned_location)
            return None
            
    def geocode_batch(self, locations: list, show_progress: bool = True) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Geocode a batch of locations with progress tracking.
        
        Args:
            locations: List of location strings
            show_progress: Whether to show progress information
            
        Returns:
            Dictionary mapping original locations to geocoding results
        """
        results = {}
        total = len(locations)
        
        for i, location in enumerate(locations):
            if show_progress and (i % 100 == 0 or i == total - 1):
                logger.info(f"Geocoding progress: {i+1}/{total} ({((i+1)/total)*100:.1f}%)")
                
            results[location] = self.geocode_location(location)
            
        # Log summary statistics
        successful = sum(1 for r in results.values() if r is not None)
        failed = total - successful
        logger.info(f"Geocoding complete: {successful}/{total} successful ({successful/total*100:.1f}%), {failed} failed")
        
        return results
        
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            'cached_locations': len(self.cache),
            'failed_locations': len(self.failed_locations)
        }

def create_spatial_query_examples():
    """
    Create example MongoDB spatial queries for documentation.
    """
    examples = {
        'find_users_near_point': {
            'description': 'Find users within 50km of New York City',
            'query': {
                "location.coordinates": {
                    "$near": {
                        "$geometry": {
                            "type": "Point",
                            "coordinates": [-74.0060, 40.7128]  # NYC coordinates [lng, lat]
                        },
                        "$maxDistance": 50000  # 50km in meters
                    }
                }
            }
        },
        'find_users_in_polygon': {
            'description': 'Find users within a geographic polygon (e.g., state boundaries)',
            'query': {
                "location.coordinates": {
                    "$geoWithin": {
                        "$geometry": {
                            "type": "Polygon",
                            "coordinates": [[
                                [-74.0, 40.7], [-74.0, 40.8], 
                                [-73.9, 40.8], [-73.9, 40.7], 
                                [-74.0, 40.7]
                            ]]
                        }
                    }
                }
            }
        },
        'aggregate_by_distance': {
            'description': 'Aggregate users by distance from a point',
            'pipeline': [
                {
                    "$geoNear": {
                        "near": {"type": "Point", "coordinates": [-74.0060, 40.7128]},
                        "distanceField": "distance_from_nyc",
                        "maxDistance": 100000,  # 100km
                        "spherical": True
                    }
                },
                {
                    "$bucket": {
                        "groupBy": "$distance_from_nyc",
                        "boundaries": [0, 10000, 25000, 50000, 100000],  # Distance buckets in meters
                        "default": "far",
                        "output": {"count": {"$sum": 1}}
                    }
                }
            ]
        }
    }
    return examples

if __name__ == "__main__":
    # Example usage and testing
    transformer = GeographicTransformer()
    
    # Test locations from the dataset
    test_locations = [
        "nyc, new york, usa",
        "stockton, california, usa", 
        "moscow, yukon territory, russia",
        "porto, v.n.gaia, portugal",
        "barcelona, barcelona, spain"
    ]
    
    print("Testing geographic transformation:")
    for location in test_locations:
        result = transformer.geocode_location(location)
        if result:
            coords = result['coordinates']
            print(f"'{location}' -> [{coords[0]:.4f}, {coords[1]:.4f}] ({result['country']})")
        else:
            print(f"'{location}' -> FAILED")
            
    print(f"\nCache stats: {transformer.get_cache_stats()}")
    
    # Print spatial query examples
    print("\nSpatial Query Examples:")
    examples = create_spatial_query_examples()
    for name, example in examples.items():
        print(f"\n{name}: {example['description']}")
        print(f"Query: {example.get('query', example.get('pipeline'))}")