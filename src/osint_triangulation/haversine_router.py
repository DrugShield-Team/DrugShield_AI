"""
DrugShield AI - Haversine Police Precinct Routing & Dispatch Calculator
=======================================================================
Re-exports police routing logic from `src.cases.police_router` to ensure
complete synchronization across all OSINT triangulation and case management modules.
"""

from __future__ import annotations

from src.cases.police_router import (
    EARTH_RADIUS_KM,
    POLICE_PRECINCTS,
    PRECINCT_ALIASES,
    calculate_estimated_eta,
    get_precinct_by_id,
    haversine_distance_km,
    normalize_precinct_id,
    route_to_nearest_precinct,
)

__all__ = [
    "EARTH_RADIUS_KM",
    "POLICE_PRECINCTS",
    "PRECINCT_ALIASES",
    "haversine_distance_km",
    "calculate_estimated_eta",
    "route_to_nearest_precinct",
    "normalize_precinct_id",
    "get_precinct_by_id",
]
