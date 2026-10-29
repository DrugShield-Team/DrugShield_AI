"""
DrugShield AI - Haversine Police Precinct Routing & Dispatch Calculator
=======================================================================
Calculates geographical great-circle distance between suspect coordinates
(resolved via EXIF GPS or passive IP telemetry) and simulated police
precincts (Precinct North & Precinct South). Recommends the optimal
jurisdictional dispatch node with estimated emergency response ETA.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

# Earth radius in kilometers
EARTH_RADIUS_KM = 6371.0088

# Pre-configured simulated police precincts
POLICE_PRECINCTS = [
    {
        "id": "PRECINCT_NORTH",
        "name": "Delhi Metro North Precinct (HQ Command)",
        "address": "Civil Lines / Mall Road, New Delhi",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "contact": "+91-11-23910001",
        "status": "ACTIVE_DISPATCH",
    },
    {
        "id": "PRECINCT_SOUTH",
        "name": "NCR Cyber & Narcotics Precinct South",
        "address": "Sector 29 / Cyber Hub, Gurugram",
        "latitude": 28.4595,
        "longitude": 77.0266,
        "contact": "+91-124-2392002",
        "status": "ACTIVE_DISPATCH",
    },
]


def haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Compute great-circle distance in kilometers using the Haversine formula.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(EARTH_RADIUS_KM * c, 2)


def calculate_estimated_eta(distance_km: float, avg_urban_speed_kmh: float = 35.0) -> int:
    """Calculate estimated rapid-response arrival ETA in minutes."""
    if distance_km <= 0.1:
        return 2
    hours = distance_km / avg_urban_speed_kmh
    minutes = int(math.ceil(hours * 60.0))
    return max(3, minutes)


def route_to_nearest_precinct(
    target_lat: float,
    target_lon: float,
    precincts: List[Dict[str, Any]] = POLICE_PRECINCTS,
) -> Dict[str, Any]:
    """
    Evaluate target coordinates against all active precincts and assign
    the closest station with calculated distance, route bearing, and response ETA.
    """
    evaluated: List[Dict[str, Any]] = []

    for precinct in precincts:
        p_lat = precinct["latitude"]
        p_lon = precinct["longitude"]
        dist = haversine_distance_km(target_lat, target_lon, p_lat, p_lon)
        eta = calculate_estimated_eta(dist)

        evaluated.append({
            "precinct_id": precinct["id"],
            "name": precinct["name"],
            "address": precinct["address"],
            "contact": precinct["contact"],
            "coordinates": {"latitude": p_lat, "longitude": p_lon},
            "distance_km": dist,
            "estimated_eta_minutes": eta,
        })

    # Sort ascending by distance
    evaluated.sort(key=lambda item: item["distance_km"])
    nearest = evaluated[0] if evaluated else None

    return {
        "target_coordinates": {
            "latitude": target_lat,
            "longitude": target_lon,
        },
        "assigned_precinct": nearest,
        "all_precinct_evaluations": evaluated,
        "dispatch_status": "READY_FOR_DISPATCH",
    }
