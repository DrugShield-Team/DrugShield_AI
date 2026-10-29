"""
DrugShield AI - Police Precinct Geo-Spatial Routing Engine
==========================================================
Maintains registered law enforcement precinct nodes (configured across demo laptops),
computes great-circle Haversine distances to target coordinates, and assigns the
absolute single nearest precinct for rapid primary tactical dispatch.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Earth mean radius in kilometers
EARTH_RADIUS_KM = 6371.0088

# ---------------------------------------------------------------------------
# Registered Police Precinct Nodes (Representing 3 Demo Laptops / Stations)
# ---------------------------------------------------------------------------
POLICE_PRECINCTS: List[Dict[str, Any]] = [
    {
        "id": "PRECINCT_NORTH",
        "node_id": "NODE_01",
        "node_index": 1,
        "name": "Delhi Metro North Precinct (HQ Command / Node 1)",
        "short_name": "Node 1: Delhi North HQ",
        "jurisdiction": "North Delhi Metropolitan & Civil Lines Tactical Zone",
        "address": "Civil Lines / Mall Road, New Delhi",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "contact": "+91-11-23910001",
        "status": "ACTIVE_PATROL",
        "frequency": "VHF-148.55 MHz",
    },
    {
        "id": "PRECINCT_SOUTH",
        "node_id": "NODE_02",
        "node_index": 2,
        "name": "NCR Cyber & Narcotics Precinct South (Node 2)",
        "short_name": "Node 2: Gurugram South",
        "jurisdiction": "NCR South & Cyber City Narcotics Division",
        "address": "Sector 29 / Cyber Hub, Gurugram",
        "latitude": 28.4595,
        "longitude": 77.0266,
        "contact": "+91-124-2392002",
        "status": "ACTIVE_PATROL",
        "frequency": "VHF-152.10 MHz",
    },
    {
        "id": "PRECINCT_EAST",
        "node_id": "NODE_03",
        "node_index": 3,
        "name": "East Delhi Rapid Interception Precinct (Node 3)",
        "short_name": "Node 3: East Delhi Transit",
        "jurisdiction": "Trans-Yamuna Rapid Response & Transit Interception",
        "address": "Anand Vihar / Patparganj Interceptor Post, East Delhi",
        "latitude": 28.6469,
        "longitude": 77.3160,
        "contact": "+91-11-22440003",
        "status": "ACTIVE_PATROL",
        "frequency": "VHF-150.80 MHz",
    },
]

# Map aliases (numbers, node IDs, names) to canonical precinct ID
PRECINCT_ALIASES: Dict[str, str] = {
    "1": "PRECINCT_NORTH",
    "node1": "PRECINCT_NORTH",
    "node_1": "PRECINCT_NORTH",
    "node_01": "PRECINCT_NORTH",
    "north": "PRECINCT_NORTH",
    "precinct_north": "PRECINCT_NORTH",
    "delhi_north": "PRECINCT_NORTH",
    "2": "PRECINCT_SOUTH",
    "node2": "PRECINCT_SOUTH",
    "node_2": "PRECINCT_SOUTH",
    "node_02": "PRECINCT_SOUTH",
    "south": "PRECINCT_SOUTH",
    "precinct_south": "PRECINCT_SOUTH",
    "gurugram": "PRECINCT_SOUTH",
    "3": "PRECINCT_EAST",
    "node3": "PRECINCT_EAST",
    "node_3": "PRECINCT_EAST",
    "node_03": "PRECINCT_EAST",
    "east": "PRECINCT_EAST",
    "precinct_east": "PRECINCT_EAST",
    "anand_vihar": "PRECINCT_EAST",
    "all": "ALL",
    "admin": "ALL",
    "hq": "ALL",
    "*": "ALL",
}


def normalize_precinct_id(raw_id: Optional[str]) -> str:
    """Normalize user input or query param to canonical precinct ID."""
    if not raw_id:
        return "ALL"
    cleaned = raw_id.strip().lower()
    return PRECINCT_ALIASES.get(cleaned, raw_id.strip().upper())


def get_precinct_by_id(precinct_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve precinct configuration by canonical ID or alias."""
    canonical = normalize_precinct_id(precinct_id)
    for p in POLICE_PRECINCTS:
        if p["id"] == canonical or p["node_id"] == canonical:
            return p
    return None


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
    precincts: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Evaluate target coordinates against all active precincts and assign
    the absolute single nearest precinct (minimum Haversine distance).
    
    The nearest precinct is designated 'ASSIGNED PRIMARY DISPATCH NODE'.
    All other precincts are marked 'STANDBY SECONDARY NODE'.
    """
    candidates = precincts if precincts is not None else POLICE_PRECINCTS
    evaluated: List[Dict[str, Any]] = []

    for precinct in candidates:
        p_lat = precinct["latitude"]
        p_lon = precinct["longitude"]
        dist = haversine_distance_km(target_lat, target_lon, p_lat, p_lon)
        eta = calculate_estimated_eta(dist)

        evaluated.append({
            "precinct_id": precinct["id"],
            "node_id": precinct.get("node_id", ""),
            "node_index": precinct.get("node_index", 1),
            "name": precinct["name"],
            "short_name": precinct.get("short_name", precinct["name"]),
            "jurisdiction": precinct.get("jurisdiction", ""),
            "address": precinct["address"],
            "contact": precinct["contact"],
            "frequency": precinct.get("frequency", "VHF"),
            "coordinates": {"latitude": p_lat, "longitude": p_lon},
            "distance_km": dist,
            "estimated_eta_minutes": eta,
            "is_primary": False,
            "dispatch_role": "STANDBY SECONDARY NODE",
        })

    # Sort strictly ascending by distance to find absolute single nearest node
    evaluated.sort(key=lambda item: item["distance_km"])
    
    nearest = evaluated[0] if evaluated else None
    if nearest:
        nearest["is_primary"] = True
        nearest["dispatch_role"] = "ASSIGNED PRIMARY DISPATCH NODE"

    return {
        "target_coordinates": {
            "latitude": target_lat,
            "longitude": target_lon,
        },
        "assigned_precinct": nearest,
        "nearest_node_id": nearest["precinct_id"] if nearest else None,
        "nearest_node_index": nearest.get("node_index", 1) if nearest else 1,
        "minimum_distance_km": nearest["distance_km"] if nearest else 0.0,
        "all_precinct_evaluations": evaluated,
        "dispatch_status": "ASSIGNED_PRIMARY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
