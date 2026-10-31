"""
Unit & Integration Tests for Active Honeypot, Passive OSINT Tracking, & Police Dispatch
"""

import io
from PIL import Image

from src.ai_pipeline.exif_extractor import _dms_to_decimal, extract_exif_metadata
from src.osint_triangulation.ip_geolocation import (
    extract_client_ip,
    generate_device_fingerprint,
    is_private_or_loopback,
    resolve_ip_location,
)
from src.osint_triangulation.haversine_router import (
    haversine_distance_km,
    route_to_nearest_precinct,
    POLICE_PRECINCTS,
)
from src.cases.state_machine import (
    STATE_ACTIVE_HONEYPOT_READY,
    STATE_PASSIVE_MONITOR,
    ThreatStateMachine,
    state_machine,
)
from src.ingestion.smart_honeypot_bot import SmartBuyerBot
from src.database.postgres_client import postgres_client


def test_dms_to_decimal_conversion():
    # 28 deg, 36 min, 50 sec North
    dms = (28, 36, 50)
    decimal = _dms_to_decimal(dms, "N")
    assert decimal is not None
    assert round(decimal, 2) == 28.61

    # South should be negative
    decimal_s = _dms_to_decimal(dms, "S")
    assert decimal_s is not None
    assert round(decimal_s, 2) == -28.61


def test_extract_exif_metadata_on_clean_image():
    # Create clean in-memory image without EXIF
    img = Image.new("RGB", (64, 64), color="red")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="JPEG")
    res = extract_exif_metadata(img_bytes.getvalue())

    assert isinstance(res, dict)
    assert res["has_exif"] is False
    assert res["has_gps"] is False
    assert res["latitude"] is None


def test_ip_geolocation_and_fingerprint():
    # Loopback detection
    assert is_private_or_loopback("127.0.0.1") is True
    assert is_private_or_loopback("10.0.0.5") is True
    assert is_private_or_loopback("192.168.1.1") is True
    assert is_private_or_loopback("8.8.8.8") is False

    headers = {
        "x-forwarded-for": "103.21.244.2, 127.0.0.1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
        "accept-language": "hi-IN,en-US;q=0.9",
        "sec-ch-ua": '"Google Chrome";v="119"',
    }
    extracted_ip = extract_client_ip(headers)
    assert extracted_ip == "103.21.244.2"

    loc = resolve_ip_location("127.0.0.1")
    assert loc["latitude"] > 0
    assert loc["city"] is not None

    fp_hash, fp_meta = generate_device_fingerprint(extracted_ip, headers)
    assert len(fp_hash) == 64
    assert fp_meta["heuristics"]["os"] == "Windows"
    assert fp_meta["heuristics"]["browser"] == "Google Chrome"


def test_haversine_distance_and_routing():
    # Distance between Delhi Precinct North (28.6139, 77.2090) and Gurugram Precinct South (28.4595, 77.0266)
    dist = haversine_distance_km(28.6139, 77.2090, 28.4595, 77.0266)
    # Approx 24-26 km
    assert 22.0 < dist < 30.0

    # Target right next to North Precinct
    routing_north = route_to_nearest_precinct(28.6140, 77.2095)
    assert routing_north["assigned_precinct"]["precinct_id"] == "PRECINCT_NORTH"
    assert routing_north["assigned_precinct"]["distance_km"] < 1.0

    # Target right next to South Precinct
    routing_south = route_to_nearest_precinct(28.4590, 77.0260)
    assert routing_south["assigned_precinct"]["precinct_id"] == "PRECINCT_SOUTH"
    assert routing_south["assigned_precinct"]["distance_km"] < 1.0


def test_three_node_precinct_routing():
    """Verify distinct 3-node demo configuration and single nearest allocation."""
    assert len(POLICE_PRECINCTS) == 3
    precinct_ids = [p["id"] for p in POLICE_PRECINCTS]
    assert "PRECINCT_NORTH" in precinct_ids
    assert "PRECINCT_SOUTH" in precinct_ids
    assert "PRECINCT_EAST" in precinct_ids

    # 1. Target near Node 1 (North)
    r1 = route_to_nearest_precinct(28.6140, 77.2092)
    assert r1["assigned_precinct"]["precinct_id"] == "PRECINCT_NORTH"
    assert r1["assigned_precinct"]["is_primary"] is True
    assert r1["assigned_precinct"]["dispatch_role"] in ["ASSIGNED PRIMARY DISPATCH NODE", "SIMULATED_PRIMARY_NODE"]
    # Secondary nodes must be standby
    for other in r1["all_precinct_evaluations"][1:]:
        assert other["is_primary"] is False
        assert other["dispatch_role"] in ["STANDBY SECONDARY NODE", "SIMULATED_STANDBY_NODE"]

    # 2. Target near Node 2 (Gurugram South)
    r2 = route_to_nearest_precinct(28.4596, 77.0268)
    assert r2["assigned_precinct"]["precinct_id"] == "PRECINCT_SOUTH"
    assert r2["assigned_precinct"]["is_primary"] is True
    assert r2["assigned_precinct"]["dispatch_role"] in ["ASSIGNED PRIMARY DISPATCH NODE", "SIMULATED_PRIMARY_NODE"]

    # 3. Target near Node 3 (East Delhi / Anand Vihar)
    r3 = route_to_nearest_precinct(28.6470, 77.3162)
    assert r3["assigned_precinct"]["precinct_id"] == "PRECINCT_EAST"
    assert r3["assigned_precinct"]["is_primary"] is True
    assert r3["assigned_precinct"]["dispatch_role"] in ["ASSIGNED PRIMARY DISPATCH NODE", "SIMULATED_PRIMARY_NODE"]


def test_websocket_targeted_dispatch_filtering():
    """Verify WebSocket pushes live alert EXCLUSIVELY to closest node and standby to others."""
    import asyncio
    from src.api.routes_honeypot import DispatchConnectionManager

    manager = DispatchConnectionManager()

    class MockWebSocket:
        def __init__(self, name):
            self.name = name
            self.received = []

        async def accept(self):
            pass

        async def send_json(self, data):
            self.received.append(data)

    ws_north = MockWebSocket("ws_north")
    ws_south = MockWebSocket("ws_south")
    ws_east = MockWebSocket("ws_east")
    ws_admin = MockWebSocket("ws_admin")

    async def run_dispatch_test():
        await manager.connect(ws_north, precinct_id="PRECINCT_NORTH")
        await manager.connect(ws_south, precinct_id="PRECINCT_SOUTH")
        await manager.connect(ws_east, precinct_id="PRECINCT_EAST")
        await manager.connect(ws_admin, precinct_id="ALL")

        # Simulate target near East Delhi Precinct (Node 3)
        dispatch_info = route_to_nearest_precinct(28.6470, 77.3162)
        assert dispatch_info["assigned_precinct"]["precinct_id"] == "PRECINCT_EAST"

        await manager.dispatch_to_nearest(dispatch_info)

        # Node 3 (East) MUST receive primary dispatch alert
        assert len(ws_east.received) == 1
        assert ws_east.received[0]["event"] == "POLICE_DISPATCH_ALERT"
        assert ws_east.received[0]["is_primary"] is True
        assert ws_east.received[0]["highlight_role"] == "ASSIGNED PRIMARY DISPATCH NODE"

        # Node 1 (North) and Node 2 (South) MUST receive standby status (NO pop-up alert)
        assert len(ws_north.received) == 1
        assert ws_north.received[0]["event"] == "POLICE_STANDBY_STATUS"
        assert ws_north.received[0]["is_primary"] is False
        assert ws_north.received[0]["highlight_role"] == "STANDBY JURISDICTION"

        assert len(ws_south.received) == 1
        assert ws_south.received[0]["event"] == "POLICE_STANDBY_STATUS"
        assert ws_south.received[0]["is_primary"] is False

        # Admin receives overview
        assert len(ws_admin.received) == 1
        assert ws_admin.received[0]["is_primary"] is True

    asyncio.run(run_dispatch_test())


def test_state_machine_threshold_accumulation(tmp_path=None):
    if tmp_path is None:
        import tempfile, pathlib
        tmp_path = pathlib.Path(tempfile.mkdtemp())
    test_db = tmp_path / "test_state.db"
    sm = ThreatStateMachine(db_path=test_db)
    entity = "suspect_vendor_99"

    # 1. First event
    ev1 = sm.evaluate_threat_event({
        "sender_id": entity,
        "chat_id": "chat_99",
        "threat_score": 0.85,
        "flagged_status": True,
        "extracted_entities": {"narcotics_detected": ["meow meow"]},
    })
    assert ev1["flag_count"] == 1
    assert ev1["current_state"] == STATE_PASSIVE_MONITOR
    assert ev1["threshold_reached"] is False

    # 2. Second event
    ev2 = sm.evaluate_threat_event({
        "sender_id": entity,
        "chat_id": "chat_99",
        "threat_score": 0.90,
        "flagged_status": True,
        "ocr_forensics": {"text_extracted": True},
    })
    assert ev2["flag_count"] == 2

    # 3. Third event
    ev3 = sm.evaluate_threat_event({
        "sender_id": entity,
        "chat_id": "chat_99",
        "threat_score": 0.75,
        "flagged_status": True,
        "qr_scan": {"qr_detected": True},
    })
    assert ev3["flag_count"] == 3
    assert ev3["current_state"] == STATE_PASSIVE_MONITOR

    # 4. Fourth event - Threshold reached!
    ev4 = sm.evaluate_threat_event({
        "sender_id": entity,
        "chat_id": "chat_99",
        "threat_score": 0.95,
        "flagged_status": True,
        "nlp_analysis": {"solicitation_intent": True},
    })
    assert ev4["flag_count"] == 4
    assert ev4["threshold_reached"] is True
    assert ev4["current_state"] == STATE_ACTIVE_HONEYPOT_READY
    assert sm.is_thread_paused("chat_99") is True


def test_smart_buyer_bot_handoff():
    bot = SmartBuyerBot(api_base_url="http://127.0.0.1:8000")
    target = "vendor_target_42"
    chat = "channel_42"

    res = bot.engage_target(entity_id=target, chat_id=chat, platform="telegram")
    assert res["entity_id"] == target
    assert "inv_" in res["tracking_token"]
    assert "/api/v1/invoice/" in res["invoice_url"]
    # Suspect dealer replies with UPI ID or QR details
    reply_res = bot.handle_target_reply(
        entity_id=target,
        chat_id=chat,
        message_text="Send advance payment to rohit@okaxis or scan QR",
        platform="telegram",
    )
    assert res["tracking_token"] in reply_res["dispatched_message"]
    assert reply_res["stage"] == "INVOICE_SENT"

    # Verify state machine transitioned to INVOICE_SENT
    st = state_machine.get_entity_state(target)
    assert st["current_state"] == "INVOICE_SENT"


def test_database_honeypot_hit_and_dispatch():
    hit_data = {
        "id": "test_hit_1",
        "tracking_token": "inv_test123",
        "ip": "127.0.0.1",
        "is_simulated": True,
        "country": "India",
        "region": "Delhi",
        "city": "New Delhi",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "isp": "Local Test ISP",
        "fingerprint_hash": "a" * 64,
        "user_agent": "TestAgent/1.0",
        "accept_language": "en",
        "heuristics": {"os": "Linux", "browser": "Python"},
    }
    hit_id = postgres_client.record_honeypot_hit(hit_data)
    assert hit_id == "test_hit_1"

    hits = postgres_client.get_recent_honeypot_hits(limit=5)
    assert any(h["id"] == "test_hit_1" for h in hits)

    disp_alert = {
        "id": "test_disp_1",
        "tracking_token": "inv_test123",
        "target_coordinates": {"latitude": 28.6139, "longitude": 77.2090},
        "assigned_precinct": {
            "precinct_id": "PRECINCT_NORTH",
            "name": "Delhi Metro North Precinct (HQ Command)",
            "distance_km": 0.5,
            "estimated_eta_minutes": 3,
        },
        "dispatch_status": "DISPATCH_RECOMMENDED",
    }
    disp_id = postgres_client.record_dispatch_alert(disp_alert)
    assert disp_id == "test_disp_1"

    alerts = postgres_client.get_recent_dispatch_alerts(limit=5)
    assert any(a["id"] == "test_disp_1" for a in alerts)
