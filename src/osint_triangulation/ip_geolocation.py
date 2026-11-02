"""
DrugShield AI - Passive IP Geolocation & High-Entropy Behavioral Fingerprinting
==============================================================================
Silently extracts visitor IP, real public IP lookup, geolocation, and high-entropy
client heuristics (User-Agent, Accept-Language, Client Hints, Canvas/WebGL hashes)
without user permission prompts.
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

# Simulated Default Coordinates (Delhi NCR center) fallback if network is completely offline
DEFAULT_SIMULATED_LOCATION = {
    "country": "India",
    "region": "Delhi",
    "city": "New Delhi",
    "latitude": 28.6139,
    "longitude": 77.2090,
    "isp": "Broadband Fiber Gateway",
}

# Cached Host Machine Public Egress IP for localhost demo runs
_CACHED_HOST_PUBLIC_IP: Optional[str] = None


def get_host_public_ip(timeout_seconds: float = 1.5) -> Optional[str]:
    """Retrieve host machine's actual public IP from lightweight IP discovery."""
    global _CACHED_HOST_PUBLIC_IP
    if _CACHED_HOST_PUBLIC_IP:
        return _CACHED_HOST_PUBLIC_IP

    endpoints = [
        "http://api.ipify.org?format=json",
        "http://ifconfig.me/all.json",
        "http://ip-api.com/json",
    ]
    for url in endpoints:
        try:
            req = Request(url, headers={"User-Agent": "DrugShield-OSINT-Probe/1.0"})
            with urlopen(req, timeout=timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                ip = data.get("ip") or data.get("ip_addr") or data.get("query")
                if ip and not is_private_or_loopback(ip):
                    _CACHED_HOST_PUBLIC_IP = ip.strip()
                    logger.info(f"[OSINT Telemetry] Discovered real host public IP: {_CACHED_HOST_PUBLIC_IP}")
                    return _CACHED_HOST_PUBLIC_IP
        except Exception:
            continue
    return None


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
    If accessing over localhost/loopback, discovers the actual public internet IP of the device.
    """
    candidate_headers = [
        "cf-connecting-ip",
        "x-real-ip",
        "x-forwarded-for",
        "true-client-ip",
        "x-client-ip",
        "forwarded",
        "x-cluster-client-ip",
    ]

    for header in candidate_headers:
        val = headers.get(header) or headers.get(header.title()) or headers.get(header.upper())
        if val:
            # First element in comma-separated list
            raw_candidates = [ip.strip() for ip in val.split(",") if ip.strip()]
            for cand in raw_candidates:
                if not is_private_or_loopback(cand):
                    return cand
            if raw_candidates:
                return raw_candidates[0]

    raw_socket_ip = client_host.strip() if client_host else "127.0.0.1"

    # If socket connection is loopback (127.0.0.1 / localhost demo test),
    # resolve the actual machine's public internet IP so evidence reports show real public IP!
    if is_private_or_loopback(raw_socket_ip):
        public_ip = get_host_public_ip()
        if public_ip:
            return public_ip

    return raw_socket_ip


def resolve_ip_location(ip_str: str, timeout_seconds: float = 2.0) -> Dict[str, Any]:
    """
    Resolve IP geolocation silently using real IP-API lookups.
    If the IP is public, resolves real city, country, ISP, and coordinates.
    """
    clean_ip = ip_str.strip() if ip_str else "127.0.0.1"

    if is_private_or_loopback(clean_ip):
        # Check if we can map host public IP
        pub = get_host_public_ip()
        if pub:
            clean_ip = pub

    if not is_private_or_loopback(clean_ip):
        try:
            url = f"http://ip-api.com/json/{clean_ip}?fields=status,message,country,regionName,city,lat,lon,isp,as"
            req = Request(url, headers={"User-Agent": "DrugShield-OSINT-Probe/1.0"})
            with urlopen(req, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if payload.get("status") == "success":
                    return {
                        "ip": clean_ip,
                        "is_simulated": False,
                        "country": payload.get("country", "India"),
                        "region": payload.get("regionName", "NCR"),
                        "city": payload.get("city", "Delhi"),
                        "latitude": float(payload.get("lat", DEFAULT_SIMULATED_LOCATION["latitude"])),
                        "longitude": float(payload.get("lon", DEFAULT_SIMULATED_LOCATION["longitude"])),
                        "isp": payload.get("isp") or payload.get("as") or "Broadband Provider",
                    }
        except Exception as exc:
            logger.debug(f"Public IP lookup notice for {clean_ip}: {exc}")

    # Fallback to urban coordinates
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
    client_telemetry: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Generate a passive high-entropy composite fingerprint hash from request headers,
    IP, and optional client-side WebGL/Canvas heuristics.
    Returns (fingerprint_hash, metadata_dict).
    """
    ua = headers.get("user-agent", headers.get("User-Agent", ""))
    accept_lang = headers.get("accept-language", headers.get("Accept-Language", ""))
    sec_ch_ua = headers.get("sec-ch-ua", headers.get("Sec-Ch-Ua", ""))
    sec_ch_platform = headers.get("sec-ch-ua-platform", headers.get("Sec-Ch-Ua-Platform", ""))

    locale_match = re.search(r"([a-zA-Z]{2,3}(?:-[a-zA-Z0-9]+)?)", accept_lang)
    primary_locale = locale_match.group(1).lower() if locale_match else "en-us"

    heuristics = parse_browser_heuristics(ua)

    # Incorporate client-side high entropy details if provided
    client_extra = ""
    if client_telemetry:
        screen_res = client_telemetry.get("screen_resolution", "")
        canvas_hash = client_telemetry.get("canvas_hash", "")
        webgl_vendor = client_telemetry.get("webgl_vendor", "")
        timezone_name = client_telemetry.get("timezone", "")
        client_extra = f"|{screen_res}|{canvas_hash}|{webgl_vendor}|{timezone_name}"
        heuristics.update(client_telemetry)

    fingerprint_seed = f"{ip}|{ua}|{accept_lang}|{sec_ch_ua}|{sec_ch_platform}{client_extra}".encode("utf-8")
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
