"""
DrugShield AI - Module 1 & 4 API: Silent Honeypot Tracking & Police Dispatch
===========================================================================
Serves silent tracking invoice landing pages, records visitor telemetry (IP,
browser heuristics, device fingerprint), calculates Haversine routing to
the nearest police precinct, commits audit logs to PostgreSQL, and broadcasts
real-time dispatch alerts to monitoring dashboards via WebSockets.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Header, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from src.cases.state_machine import (
    STATE_DISPATCH_INITIATED,
    STATE_TARGET_GEO_LOCATED,
    state_machine,
)
from src.database.postgres_client import postgres_client
from src.cases.police_router import (
    POLICE_PRECINCTS,
    get_precinct_by_id,
    normalize_precinct_id,
    route_to_nearest_precinct,
)
from src.osint_triangulation.ip_geolocation import (
    extract_client_ip,
    generate_device_fingerprint,
    resolve_ip_location,
)

logger = logging.getLogger("DrugShield.HoneypotRoutes")

router = APIRouter(tags=["Honeypot & Police Dispatch"])


class DispatchConnectionManager:
    """
    Manages active WebSocket connections across multi-PC demo nodes.
    Tracks each connected client's assigned precinct/node ID and routes live
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
        Dynamically identify the single nearest precinct and push the live
        pop-up alert ONLY to that specific node's dashboard.
        Standby nodes receive standby notifications without triggering the priority alert banner.
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


INVOICE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Checkout / DirectPay UPI Receipt</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background-color: #f1f5f9; color: #1e293b; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 16px; }
        .checkout-container { background: #ffffff; width: 100%; max-width: 430px; border-radius: 20px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.02); border: 1px solid #e2e8f0; overflow: hidden; }
        .checkout-header { padding: 20px 24px 16px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #f1f5f9; }
        .brand-badge { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px; color: #0f172a; }
        .brand-badge svg { color: #2563eb; }
        .secure-pill { background: #eff6ff; color: #2563eb; font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 9999px; letter-spacing: 0.3px; }
        
        .hero-section { padding: 26px 24px 20px; text-align: center; }
        .success-icon-wrap { width: 56px; height: 56px; background: #dcfce7; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 14px; }
        .success-icon-wrap svg { color: #16a34a; }
        .hero-title { font-size: 13px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
        .hero-amount { font-size: 32px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; margin-bottom: 6px; }
        .status-badge { display: inline-flex; align-items: center; gap: 6px; background: #ecfdf5; color: #059669; font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 9999px; }
        
        .order-summary { margin: 0 24px 20px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; padding: 16px; }
        .summary-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 13px; }
        .summary-row:last-child { margin-bottom: 0; padding-top: 10px; border-top: 1px dashed #cbd5e1; }
        .summary-label { color: #64748b; }
        .summary-val { font-weight: 600; color: #0f172a; }
        .summary-val.token { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; color: #2563eb; }
        
        .actions-section { padding: 0 24px 24px; }
        .btn-primary { width: 100%; background: #2563eb; color: #ffffff; border: none; border-radius: 12px; padding: 14px; font-size: 14px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; transition: all 0.2s ease; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2); }
        .btn-primary:hover { background: #1d4ed8; }
        .btn-primary:active { transform: scale(0.98); }
        .btn-secondary { width: 100%; margin-top: 10px; background: #ffffff; color: #475569; border: 1px solid #cbd5e1; border-radius: 12px; padding: 12px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; }
        .btn-secondary:hover { background: #f8fafc; border-color: #94a3b8; }
        
        .checkout-footer { background: #f8fafc; border-top: 1px solid #e2e8f0; padding: 14px 24px; text-align: center; }
        .footer-note { font-size: 11px; color: #94a3b8; line-height: 1.5; }
        .footer-secure { display: flex; align-items: center; justify-content: center; gap: 6px; font-size: 11px; font-weight: 600; color: #10b981; margin-top: 4px; }
        
        .toast { display: none; position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #0f172a; color: #fff; padding: 10px 20px; border-radius: 9999px; font-size: 13px; font-weight: 500; box-shadow: 0 10px 25px rgba(0,0,0,0.2); z-index: 100; }
    </style>
</head>
<body>
    <div class="checkout-container">
        <div class="checkout-header">
            <div class="brand-badge">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                <span>DirectPay UPI Checkout</span>
            </div>
            <span class="secure-pill">VERIFIED P2P</span>
        </div>

        <div class="hero-section">
            <div class="success-icon-wrap">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <div class="hero-title">Payment Confirmation</div>
            <div class="hero-amount">INR 3,500.00</div>
            <div class="status-badge">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                Token Advance Released
            </div>
        </div>

        <div class="order-summary">
            <div class="summary-row">
                <span class="summary-label">Order Reference:</span>
                <span class="summary-val token">{token}</span>
            </div>
            <div class="summary-row">
                <span class="summary-label">Date & Time:</span>
                <span class="summary-val">{date_str}</span>
            </div>
            <div class="summary-row">
                <span class="summary-label">Payment Channel:</span>
                <span class="summary-val">UPI Instant Clearing (P2P)</span>
            </div>
            <div class="summary-row">
                <span class="summary-label">Delivery Note:</span>
                <span class="summary-val" style="color: #059669;">Awaiting GPS Drop Pin</span>
            </div>
            <div class="summary-row">
                <span class="summary-label" style="font-weight: 700; color: #0f172a;">Total Amount Settled:</span>
                <span class="summary-val" style="font-size: 14px; font-weight: 700; color: #059669;">INR 3,500.00</span>
            </div>
        </div>

        <div class="actions-section">
            <button class="btn-primary" onclick="showToast('Official payment receipt downloaded successfully.')">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download Receipt (PDF)
            </button>
            <button class="btn-secondary" onclick="showToast('Payment verification link copied to clipboard.')">
                Share Transaction Copy
            </button>
        </div>

        <div class="checkout-footer">
            <div class="footer-secure">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                <span>256-Bit Encrypted UPI Transaction</span>
            </div>
            <p class="footer-note" style="margin-top: 4px;">
                Transaction Ref: {token}<br>
                Official clearing confirmation. Please share the drop pin once verified.
            </p>
        </div>
    </div>

    <div id="toast" class="toast">Action completed successfully</div>

    <script>
        function showToast(msg) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.style.display = 'block';
            setTimeout(() => { t.style.display = 'none'; }, 3000);
        }
    </script>
</body>
</html>
"""


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
    """
    Silent honeypot tracking route:
    1. Extracts client IP & headers without browser permissions.
    2. Resolves geolocation and generates device fingerprint.
    3. Calculates nearest police precinct via Haversine formula across 3 demo nodes.
    4. Records audit logs to PostgreSQL / SQLite fallback.
    5. Advances state machine to TARGET_GEO_LOCATED and DISPATCH_INITIATED.
    6. Dispatches real-time pop-up alert EXCLUSIVELY to the absolute single nearest precinct node.
    7. Serves clean decoy invoice receipt to the target.
    """
    headers = dict(request.headers)
    client_host = request.client.host if request.client else "127.0.0.1"
    ip = extract_client_ip(headers, client_host)

    # 1. Resolve Location & Fingerprint
    geo = resolve_ip_location(ip)
    fp_hash, fp_meta = generate_device_fingerprint(ip, headers)

    hit_record = {
        "tracking_token": tracking_token,
        "ip": ip,
        "is_simulated": geo.get("is_simulated", True),
        "country": geo.get("country", "India"),
        "region": geo.get("region", "Delhi"),
        "city": geo.get("city", "New Delhi"),
        "latitude": geo.get("latitude", 28.6139),
        "longitude": geo.get("longitude", 77.2090),
        "isp": geo.get("isp", "Broadband Local"),
        "fingerprint_hash": fp_hash,
        "user_agent": fp_meta.get("user_agent", ""),
        "accept_language": fp_meta.get("accept_language", ""),
        "heuristics": fp_meta.get("heuristics", {}),
    }

    # Proximity override for multi-PC presentation testing
    if target_node:
        sim_precinct = get_precinct_by_id(target_node)
        if sim_precinct:
            hit_record["latitude"] = sim_precinct["latitude"] + 0.0002
            hit_record["longitude"] = sim_precinct["longitude"] + 0.0002
            hit_record["city"] = f"{sim_precinct['address']} (Sector Test)"
    elif lat is not None and lon is not None:
        hit_record["latitude"] = lat
        hit_record["longitude"] = lon
        hit_record["city"] = f"Coordinates ({lat:.4f}, {lon:.4f})"

    # 2. Commit visitor hit to database
    hit_id = postgres_client.record_honeypot_hit(hit_record)

    # 3. Haversine Police Routing - Calculate nearest among all 3 demo nodes
    dispatch_info = route_to_nearest_precinct(
        target_lat=hit_record["latitude"],
        target_lon=hit_record["longitude"],
    )
    dispatch_info["tracking_token"] = tracking_token
    dispatch_info["hit_id"] = hit_id
    dispatch_info["visitor_ip"] = ip
    dispatch_info["city"] = hit_record["city"]
    dispatch_info["timestamp"] = datetime.now(timezone.utc).isoformat()

    # 4. Commit police dispatch alert to database
    dispatch_id = postgres_client.record_dispatch_alert(dispatch_info)
    dispatch_info["dispatch_id"] = dispatch_id

    # 5. Advance State Machine
    state_machine.transition_state(
        entity_id=tracking_token,
        new_state=STATE_TARGET_GEO_LOCATED,
        reason=f"Target accessed honeypot invoice link. IP: {ip}, Locality: {hit_record['city']}",
        details=hit_record,
    )
    state_machine.transition_state(
        entity_id=tracking_token,
        new_state=STATE_DISPATCH_INITIATED,
        reason=f"Assigned to {dispatch_info['assigned_precinct']['name']} ({dispatch_info['assigned_precinct']['distance_km']} km)",
        details=dispatch_info,
    )

    # 6. Targeted Dispatch - Pushes live pop-up alert ONLY to the single closest node
    await dispatch_manager.dispatch_to_nearest(dispatch_info)

    logger.info(
        f"[Honeypot Hit] Token: {tracking_token} | IP: {ip} | City: {hit_record['city']} | "
        f"Assigned Primary Node: {dispatch_info['assigned_precinct']['name']} ({dispatch_info['assigned_precinct']['distance_km']} km)"
    )

    if format == "json" or "application/json" in headers.get("accept", ""):
        return JSONResponse(content={
            "status": "success",
            "invoice_token": tracking_token,
            "dispatch": dispatch_info,
        })

    # Render benign decoy invoice
    now_str = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")
    html_content = INVOICE_HTML_TEMPLATE.replace("{token}", tracking_token).replace("{date_str}", now_str)
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/api/v1/dispatch/alerts")
def list_dispatch_alerts(limit: int = 50):
    """Retrieve recent police dispatch alerts."""
    return {
        "status": "success",
        "alerts": postgres_client.get_recent_dispatch_alerts(limit=limit),
    }


@router.get("/api/v1/honeypot/logs")
def list_honeypot_hits(limit: int = 50):
    """Retrieve captured honeypot hits."""
    return {
        "status": "success",
        "hits": postgres_client.get_recent_honeypot_hits(limit=limit),
    }


@router.get("/api/v1/state-machine/{entity_id}")
def get_entity_state_machine(entity_id: str):
    """Query state machine status and flag count for an entity."""
    return state_machine.get_entity_state(entity_id)


@router.get("/api/v1/cases/{token_or_id}/report", response_class=HTMLResponse)
@router.get("/api/v1/cases/{token_or_id}/docket", response_class=HTMLResponse)
@router.get("/api/v1/evidence/{token_or_id}", response_class=HTMLResponse)
def get_forensic_case_report(
    token_or_id: str,
    request: Request,
    format: Optional[str] = Query(default=None),
):
    """
    Law Enforcement Digital Evidence Docket Generator:
    Aggregates suspect metadata, chat escalation transcript, OSINT device telemetry,
    and Haversine police precinct routing into a legal-grade forensic dossier.
    """
    from src.reporting.case_docket_generator import compile_case_docket, render_docket_html

    docket = compile_case_docket(token_or_id)
    headers = dict(request.headers)

    if format == "json" or "application/json" in headers.get("accept", ""):
        return JSONResponse(content=docket)

    html_content = render_docket_html(docket)
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/api/v1/dispatch/precincts")
def list_registered_precincts():
    """Retrieve all configured police precinct dispatch nodes."""
    return {
        "status": "success",
        "count": len(POLICE_PRECINCTS),
        "precincts": POLICE_PRECINCTS,
    }


@router.websocket("/api/v1/ws/dispatch")
async def websocket_dispatch_stream(
    websocket: WebSocket,
    precinct_id: Optional[str] = Query(default=None),
    node: Optional[str] = Query(default=None),
):
    """
    WebSocket stream streaming live police precinct dispatch alerts.
    Supports node filtering via ?precinct_id=... or ?node=1/2/3.
    Push alerts trigger exclusively on the single closest precinct node.
    """
    selected_node = precinct_id or node or "ALL"
    await dispatch_manager.connect(websocket, precinct_id=selected_node)
    try:
        norm_id = normalize_precinct_id(selected_node)
        # Send initial confirmation with node binding
        await websocket.send_json({
            "event": "CONNECTED",
            "message": "Connected to DrugShield AI Police Dispatch WebSocket Stream",
            "assigned_client_node": norm_id,
            "registered_precincts": [p["id"] for p in POLICE_PRECINCTS],
        })
        while True:
            # Listen for client actions (e.g. changing assigned node from dropdown)
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
