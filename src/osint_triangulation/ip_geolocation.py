"""
DrugShield AI - Passive IP Geolocation & Behavioral Fingerprinting
==================================================================
Silently extracts visitor IP, geolocation (simulated fallback for loopbacks),
and non-intrusive HTTP header details (User-Agent, Accept-Language, Client Hints)
to construct an OSINT telemetry profile without user permission prompts.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
from typing import Any, Dict, Optional, Tuple
from urllib.request import Request, urlopen

logger = logging.getLogger("DrugShield.IPGeolocation")

# Simulated Default Coordinates (Delhi NCR center) for local/loopback simulations
DEFAULT_SIMULATED_LOCATION = {
    "country": "India",
    "region": "Delhi",
    "city": "New Delhi",
    "latitude": 28.6139,
    "longitude": 77.2090,
    "isp": "Simulated Broadband Local",
}


def is_private_or_loopback(ip_str: str) -> bool:
    """Check whether an IP address is loopback, link-local, or private RFC1918."""
    if not ip_str:
        return True
    try:
        ip = ipaddress.ip_address(ip_str.strip())
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return True


def extract_client_ip(headers: Dict[str, str], client_host: Optional[str] = None) -> str:
    """
    Extract the best candidate IP address from forwarding headers or direct socket connection.
    """
    for header in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
        val = headers.get(header) or headers.get(header.title()) or headers.get(header.upper())
        if val:
            # First element in comma-separated list
            ip_candidate = val.split(",")[0].strip()
            if ip_candidate:
                return ip_candidate
    return client_host.strip() if client_host else "127.0.0.1"


def resolve_ip_location(ip_str: str, timeout_seconds: float = 2.0) -> Dict[str, Any]:
    """
    Resolve IP geolocation silently.
    If the IP is local or private, returns simulated urban location coordinates.
    """
    clean_ip = ip_str.strip() if ip_str else "127.0.0.1"
    if is_private_or_loopback(clean_ip):
        return {
            "ip": clean_ip,
            "is_simulated": True,
            **DEFAULT_SIMULATED_LOCATION,
        }

    # Public IP: Attempt lightweight HTTP IP-API lookup with quick timeout
    try:
        url = f"http://ip-api.com/json/{clean_ip}?fields=status,message,country,regionName,city,lat,lon,isp"
        req = Request(url, headers={"User-Agent": "DrugShield-OSINT-Probe/1.0"})
        with urlopen(req, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "success":
                return {
                    "ip": clean_ip,
                    "is_simulated": False,
                    "country": payload.get("country", "Unknown"),
                    "region": payload.get("regionName", "Unknown"),
                    "city": payload.get("city", "Unknown"),
                    "latitude": float(payload.get("lat", DEFAULT_SIMULATED_LOCATION["latitude"])),
                    "longitude": float(payload.get("lon", DEFAULT_SIMULATED_LOCATION["longitude"])),
                    "isp": payload.get("isp", "Unknown ISP"),
                }
    except Exception as exc:
        logger.debug(f"Public IP lookup error for {clean_ip}: {exc}")

    # Fallback if external API is unreachable or rate-limited
    return {
        "ip": clean_ip,
        "is_simulated": True,
        **DEFAULT_SIMULATED_LOCATION,
    }


def parse_browser_heuristics(user_agent: str) -> Dict[str, str]:
    """Parse non-intrusive operating system and browser engine heuristics."""
    ua = user_agent.lower()
    os_name = "Unknown OS"
    if "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua:
        os_name = "iOS"
    elif "windows" in ua:
        os_name = "Windows"
    elif "macintosh" in ua or "mac os" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"

    browser = "Unknown Browser"
    if "edg" in ua:
        browser = "Microsoft Edge"
    elif "chrome" in ua and "safari" in ua:
        browser = "Google Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Apple Safari"
    elif "firefox" in ua:
        browser = "Mozilla Firefox"

    device_type = "Desktop"
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        device_type = "Mobile"
    elif "tablet" in ua or "ipad" in ua:
        device_type = "Tablet"

    return {
        "os": os_name,
        "browser": browser,
        "device_type": device_type,
    }


def generate_device_fingerprint(
    ip: str,
    headers: Dict[str, str],
) -> Tuple[str, Dict[str, Any]]:
    """
    Generate a passive composite fingerprint hash from request headers and IP.
    Returns (fingerprint_hash, metadata_dict).
    """
    ua = headers.get("user-agent", headers.get("User-Agent", ""))
    accept_lang = headers.get("accept-language", headers.get("Accept-Language", ""))
    sec_ch_ua = headers.get("sec-ch-ua", headers.get("Sec-Ch-Ua", ""))
    sec_ch_platform = headers.get("sec-ch-ua-platform", headers.get("Sec-Ch-Ua-Platform", ""))

    # Normalize primary language code
    locale_match = re.search(r"([a-zA-Z]{2,3}(?:-[a-zA-Z0-9]+)?)", accept_lang)
    primary_locale = locale_match.group(1).lower() if locale_match else "en-us"

    heuristics = parse_browser_heuristics(ua)

    # Hash the composite string
    fingerprint_seed = f"{ip}|{ua}|{accept_lang}|{sec_ch_ua}|{sec_ch_platform}".encode("utf-8")
    fingerprint_hash = hashlib.sha256(fingerprint_seed).hexdigest()

    metadata = {
        "fingerprint_hash": fingerprint_hash,
        "user_agent": ua,
        "accept_language": accept_lang,
        "primary_locale": primary_locale,
        "sec_ch_ua": sec_ch_ua,
        "sec_ch_platform": sec_ch_platform,
        "heuristics": heuristics,
    }

    return fingerprint_hash, metadata
