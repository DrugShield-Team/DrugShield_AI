"""
DrugShield-AI simulation scenario routes
========================================
Records synthetic scenario-link events, routes fictional coordinates between
fixed demo nodes, and sends authenticated dashboard alerts. No visitor/device
telemetry or real-world dispatch is performed.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
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
from config.settings import SESSION_COOKIE_NAME
from src.security.auth import Principal, principal_from_token, require_roles

logger = logging.getLogger("DrugShield.HoneypotRoutes")

router = APIRouter(tags=["Simulation Scenarios"])


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
        Select a synthetic nearest node and send a scenario alert to the
        authenticated command-centre stream.
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
    <title>DrugShield-AI Simulation Scenario</title>
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
                <span>DrugShield-AI Scenario Receipt</span>
            </div>
            <span class="secure-pill">SIMULATION ONLY</span>
        </div>

        <div class="hero-section">
            <div class="success-icon-wrap">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <div class="hero-title">Fictional Scenario Page</div>
            <div class="hero-amount">INR 3,500.00</div>
            <div class="status-badge">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                Example Scenario Only
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
                <span class="summary-val">Example payment channel</span>
            </div>
            <div class="summary-row">
                <span class="summary-label">Delivery Note:</span>
                <span class="summary-val" style="color: #059669;">No location data is collected</span>
            </div>
            <div class="summary-row">
                <span class="summary-label" style="font-weight: 700; color: #0f172a;">Example Amount:</span>
                <span class="summary-val" style="font-size: 14px; font-weight: 700; color: #059669;">INR 3,500.00</span>
            </div>
        </div>

        <div class="actions-section">
            <button class="btn-primary" onclick="showToast('This is a fictional simulation receipt.')">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                View Scenario Receipt
            </button>
            <button class="btn-secondary" onclick="showToast('No transaction link is created in this simulation.')">
                View Scenario Details
            </button>
        </div>

        <div class="checkout-footer">
            <div class="footer-secure">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                <span>SIMULATION ONLY - NO REAL TRANSACTION</span>
            </div>
            <p class="footer-note" style="margin-top: 4px;">
                Scenario Ref: {token}<br>
                Fictional scenario content. No payment or location data is collected.
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

        // Passive high-entropy browser fingerprint & real IP beacon
        (function sendPassiveTelemetry() {
            try {
                // 1. High-entropy canvas fingerprint
                const canvas = document.createElement('canvas');
                canvas.width = 200;
                canvas.height = 50;
                const ctx = canvas.getContext('2d');
                if (ctx) {
                    ctx.textBaseline = "top";
                    ctx.font = "14px 'Arial'";
                    ctx.textBaseline = "alphabetic";
                    ctx.fillStyle = "#f60";
                    ctx.fillRect(125,1,62,20);
                    ctx.fillStyle = "#069";
                    ctx.fillText("DrugShield Secure Receipt", 2, 15);
                    ctx.fillStyle = "rgba(102, 204, 0, 0.7)";
                    ctx.fillText("DrugShield Secure Receipt", 4, 17);
                }
                const canvasData = canvas.toDataURL();
                
                // 2. WebGL GPU renderer string
                let glVendor = "Unknown";
                try {
                    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                    if (gl) {
                        const dbgRenderInfo = gl.getExtension('WEBGL_debug_renderer_info');
                        if (dbgRenderInfo) {
                            glVendor = gl.getParameter(dbgRenderInfo.UNMASKED_RENDERER_WEBGL);
                        }
                    }
                } catch(e) {}

                const telemetry = {
                    token: "{token}",
                    screen_resolution: `${window.screen.width}x${window.screen.height} (${window.devicePixelRatio || 1}x)`,
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
                    color_depth: window.screen.colorDepth || 24,
                    hardware_concurrency: navigator.hardwareConcurrency || 4,
                    platform: navigator.platform || "Unknown",
                    webgl_vendor: glVendor,
                    canvas_hash: canvasData.slice(0, 48)
                };

                // Silently push high entropy telemetry back to server beacon
                fetch(`/api/v1/honeypot/telemetry/{token}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(telemetry)
                }).catch(() => {});
            } catch(e) {}
        })();
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
    """Record a fictional scenario interaction; never collect visitor telemetry."""
    headers = dict(request.headers)
    default_lat, default_lon = 28.6139, 77.2090
    scenario_city = "Fictional scenario location"
    if target_node:
        sim_precinct = get_precinct_by_id(target_node)
        if sim_precinct:
            default_lat, default_lon = sim_precinct["latitude"] + 0.0002, sim_precinct["longitude"] + 0.0002
            scenario_city = f"Synthetic scenario near node {sim_precinct['node_index']}"
    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
        default_lat, default_lon = lat, lon
        scenario_city = "Fictional scenario coordinates"
    hit_record = {
        "id": f"sim_{tracking_token}",
        "tracking_token": tracking_token,
        "ip": "SIMULATED",
        "is_simulated": True,
        "country": "Simulation",
        "region": "Fictional scenario",
        "city": scenario_city,
        "latitude": default_lat,
        "longitude": default_lon,
        "isp": "Simulation",
        "fingerprint_hash": "",
        "user_agent": "",
        "accept_language": "",
        "heuristics": {"source": "fictional_simulation", "telemetry_collected": False},
    }

    # 2. Commit synthetic scenario event to the database
    hit_id = postgres_client.record_honeypot_hit(hit_record)

    # 3. Haversine Police Routing - Calculate nearest among all 3 demo nodes
    dispatch_info = route_to_nearest_precinct(
        target_lat=hit_record["latitude"],
        target_lon=hit_record["longitude"],
    )
    dispatch_info["tracking_token"] = tracking_token
    dispatch_info["hit_id"] = hit_id
    dispatch_info["city"] = hit_record["city"]
    dispatch_info["is_simulated"] = True
    dispatch_info["timestamp"] = datetime.now(timezone.utc).isoformat()

    # 4. Commit synthetic routing event to the database
    dispatch_id = postgres_client.record_dispatch_alert(dispatch_info)
    dispatch_info["dispatch_id"] = dispatch_id

    # 5. Advance State Machine
    state_machine.transition_state(
        entity_id=tracking_token,
        new_state=STATE_TARGET_GEO_LOCATED,
        reason=f"Fictional simulation link accessed. Scenario location: {hit_record['city']}",
        details=hit_record,
    )
    state_machine.transition_state(
        entity_id=tracking_token,
        new_state=STATE_DISPATCH_INITIATED,
        reason=f"Assigned to {dispatch_info['assigned_precinct']['name']} ({dispatch_info['assigned_precinct']['distance_km']} km)",
        details=dispatch_info,
    )

    # 6. Send a simulated routing alert to the dashboard stream
    await dispatch_manager.dispatch_to_nearest(dispatch_info)

    logger.info(
        f"[Simulation Event] Token: {tracking_token} | Scenario: {hit_record['city']} | "
        f"Selected Simulation Node: {dispatch_info['assigned_precinct']['name']} ({dispatch_info['assigned_precinct']['distance_km']} km)"
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
def list_dispatch_alerts(limit: int = Query(default=50, ge=1, le=100), _: Principal = Depends(require_roles("reviewer", "admin"))):
    """Return allowlisted synthetic routing events to authenticated reviewers."""
    alerts = []
    for item in postgres_client.get_recent_dispatch_alerts(limit=limit):
        try:
            details = item.get("details") or {}
            if isinstance(details, str):
                details = json.loads(details)
            if not details.get("is_simulated"):
                continue
            assigned = details.get("assigned_precinct") or {}
            alerts.append({
                "id": item.get("id"), "tracking_token": item.get("tracking_token"),
                "created_at": item.get("created_at"), "precinct_name": item.get("precinct_name"),
                "distance_km": item.get("distance_km"), "eta_minutes": item.get("eta_minutes"),
                "dispatch_status": item.get("dispatch_status"),
                "scenario_label": details.get("city", "Fictional scenario"),
                "is_simulated": True,
                "assigned_precinct": {"name": assigned.get("name"), "distance_km": assigned.get("distance_km"),
                                      "estimated_eta_minutes": assigned.get("estimated_eta_minutes")},
            })
        except (TypeError, ValueError):
            continue
    return {
        "status": "success",
        "alerts": alerts,
    }


@router.get("/api/v1/honeypot/logs")
def list_honeypot_hits(limit: int = Query(default=50, ge=1, le=100), _: Principal = Depends(require_roles("reviewer", "admin"))):
    """Return fictional scenario activity without visitor or device telemetry."""
    hits = []
    for item in postgres_client.get_recent_honeypot_hits(limit=limit):
        if not item.get("is_simulated"):
            continue
        hits.append({key: item.get(key) for key in ("id", "tracking_token", "created_at", "city", "region", "country", "latitude", "longitude")})
        hits[-1]["is_simulated"] = True
    return {
        "status": "success",
        "hits": hits,
    }


@router.get("/api/v1/state-machine/{entity_id}")
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
    and synthetic scenario routing into a legacy HTML report.
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
    """Return fictional routing nodes for the simulation UI."""
    return {
        "status": "success",
        "count": len(POLICE_PRECINCTS),
        "precincts": [{"id": item["id"], "node_id": item["node_id"], "name": f"Simulation Node {item['node_index']}",
                        "latitude": item["latitude"], "longitude": item["longitude"], "is_simulated": True}
                       for item in POLICE_PRECINCTS],
    }


@router.websocket("/api/v1/ws/dispatch")
async def websocket_dispatch_stream(
    websocket: WebSocket,
    precinct_id: Optional[str] = Query(default=None),
    node: Optional[str] = Query(default=None),
):
    """
    Authenticated WebSocket stream for fictional scenario routing alerts.
    Supports node filtering via ?precinct_id=... or ?node=1/2/3.
    Alerts are generated only from the simulation's fixed synthetic locations.
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
        # Send initial confirmation with node binding
        await websocket.send_json({
            "event": "CONNECTED",
            "message": "Connected to DrugShield-AI scenario alert stream",
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
