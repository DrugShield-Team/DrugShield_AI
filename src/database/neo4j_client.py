"""
DrugShield AI - Module 4: Neo4j Graph Database Client (neo4j_client.py)
========================================================================
Triangulates threat entities and persists nodes and edges into Neo4j graph database:
- Nodes: :Suspect, :ChatMessage, :NarcoticSubstance, :UPI_Account, :BankAccount, :GeoLocation
- Edges: [:SENT], [:SOLICITED], [:USES_UPI], [:USES_ACCOUNT], [:DEAD_DROP_AT]
Maintains safe local graph export ledger in `data/raw/neo4j_graph_export.jsonl` if Neo4j is offline.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent.parent
PROJECT_ROOT = SRC_DIR.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
GRAPH_EXPORT_FILE = RAW_DIR / "neo4j_graph_export.jsonl"

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "drugshield_secret")

logger = logging.getLogger("DrugShield.Neo4j")

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None


class Neo4jClient:
    def __init__(self, uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD):
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None
        self._connected = False

        if GraphDatabase is not None:
            try:
                self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
                # Verify connectivity
                with self.driver.session() as session:
                    session.run("RETURN 1")
                self._connected = True
                print(f"[Neo4j Client] Connected successfully to {self.uri}")
            except Exception as e:
                self._connected = False
                print(f"[Neo4j Notice] Neo4j server offline at {self.uri}. Operating in Local Graph Export mode.")
        else:
            print("[Neo4j Notice] 'neo4j' Python package not installed. Operating in Local Graph Export mode.")

    def push_threat_record(self, record: Dict[str, Any]) -> bool:
        """
        Pushes a flagged threat message and its extracted entities into the Neo4j graph.
        """
        RAW_DIR.mkdir(parents=True, exist_ok=True)

        msg_id = record.get("id") or f"msg_{Date_now()}"
        platform = record.get("platform", "unknown")
        timestamp = record.get("timestamp", "")
        sender = record.get("sender_id") or record.get("sender_username") or "unknown_suspect"
        content = record.get("message_text") or record.get("message_body") or ""
        threat_score = float(record.get("threat_score") or record.get("risk_score") or 0.0)

        entities = record.get("extracted_entities", {})
        upis = entities.get("upi_ids", [])
        banks = entities.get("bank_accounts", [])
        drugs = entities.get("narcotics_detected", [])
        geos = entities.get("gps_coordinates", [])

        # 1. Always record in Local Graph Export Ledger
        graph_entry = {
            "type": "GRAPH_TRANSACTION",
            "message_id": msg_id,
            "platform": platform,
            "timestamp": timestamp,
            "threat_score": threat_score,
            "nodes": {
                "Suspect": {"id": sender, "platform": platform},
                "ChatMessage": {"id": msg_id, "text": content[:120], "threat_score": threat_score},
                "UPI_Accounts": upis,
                "BankAccounts": banks,
                "Narcotics": drugs,
                "GeoLocations": geos
            },
            "relationships": [
                {"from": sender, "to": msg_id, "type": "SENT"},
                *[{"from": msg_id, "to": u, "type": "USES_UPI"} for u in upis],
                *[{"from": msg_id, "to": b, "type": "USES_ACCOUNT"} for b in banks],
                *[{"from": msg_id, "to": d, "type": "SOLICITED"} for d in drugs],
                *[{"from": msg_id, "to": g, "type": "DEAD_DROP_AT"} for g in geos]
            ]
        }

        try:
            with open(GRAPH_EXPORT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(graph_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to append to graph export file: {e}")

        # 2. Push to live Neo4j instance if active
        if self._connected and self.driver:
            try:
                cypher_query = """
                MERGE (s:Suspect {id: $sender_id})
                  ON CREATE SET s.platform = $platform, s.first_seen = $timestamp
                  ON MATCH SET s.last_seen = $timestamp

                MERGE (m:ChatMessage {id: $msg_id})
                  ON CREATE SET m.text = $text, m.threat_score = $threat_score, m.timestamp = $timestamp

                MERGE (s)-[:SENT]->(m)

                FOREACH (upi IN $upis |
                  MERGE (u:UPI_Account {vpa: upi})
                  MERGE (m)-[:USES_UPI]->(u)
                  MERGE (s)-[:ASSOCIATED_UPI]->(u)
                )

                FOREACH (bank IN $banks |
                  MERGE (b:BankAccount {acc: bank})
                  MERGE (m)-[:USES_ACCOUNT]->(b)
                )

                FOREACH (drug IN $drugs |
                  MERGE (d:NarcoticSubstance {name: drug})
                  MERGE (m)-[:SOLICITED]->(d)
                )
                """
                with self.driver.session() as session:
                    session.run(cypher_query, {
                        "sender_id": sender,
                        "platform": platform,
                        "timestamp": timestamp,
                        "msg_id": msg_id,
                        "text": content,
                        "threat_score": threat_score,
                        "upis": upis,
                        "banks": banks,
                        "drugs": drugs
                    })
                print(f"[Neo4j Client] [OK] Successfully mapped threat graph in Neo4j: {msg_id}")
                return True
            except Exception as e:
                print(f"[-] Neo4j transaction error: {e}")
                return False

        print(f"[Neo4j Client]  Graph Transaction ledgered to: data/raw/{GRAPH_EXPORT_FILE.name}")
        return True


    def push_triangulation_telemetry(self, telemetry: Dict[str, Any]) -> bool:
        """
        Pushes a dual-layer OSINT triangulation event (Passive IP / Active GPS)
        and associated network/spatial nodes into the Neo4j graph.
        """
        RAW_DIR.mkdir(parents=True, exist_ok=True)

        token = telemetry.get("tracking_token", "unknown_token")
        suspect = telemetry.get("suspect_id") or telemetry.get("entity_id") or "unknown_suspect"
        ip = telemetry.get("ip", "127.0.0.1")
        isp = telemetry.get("isp", "Unknown ISP")
        ua = telemetry.get("user_agent", "")
        city = telemetry.get("city", "Unknown City")
        region = telemetry.get("region", "")
        country = telemetry.get("country", "")
        lat = float(telemetry.get("latitude") or 0.0)
        lon = float(telemetry.get("longitude") or 0.0)
        accuracy = telemetry.get("accuracy_meters")
        layer = telemetry.get("triangulation_layer", "LAYER_1_PASSIVE_IP")
        fp_hash = telemetry.get("fingerprint_hash", "")
        timestamp = telemetry.get("timestamp", "")
        precinct_info = telemetry.get("assigned_precinct") or {}
        precinct_id = precinct_info.get("precinct_id") or precinct_info.get("id") or "DELHI-CENTRAL-HQ"
        precinct_name = precinct_info.get("name") or "Central Command"
        dist = float(precinct_info.get("distance_km") or 0.0)

        graph_entry = {
            "type": "TRIANGULATION_TELEMETRY",
            "tracking_token": token,
            "suspect_id": suspect,
            "triangulation_layer": layer,
            "timestamp": timestamp,
            "nodes": {
                "Suspect": {"id": suspect},
                "HoneypotLink": {"token": token, "layer": layer, "timestamp": timestamp},
                "NetworkProfile": {"ip": ip, "isp": isp, "fingerprint_hash": fp_hash, "user_agent": ua[:120] if ua else ""},
                "GeoLocation": {"latitude": lat, "longitude": lon, "city": city, "region": region, "country": country, "accuracy_meters": accuracy, "layer": layer},
                "Precinct": {"id": precinct_id, "name": precinct_name, "distance_km": dist}
            },
            "relationships": [
                {"from": suspect, "to": token, "type": "TRIGGERED_HONEYPOT"},
                {"from": token, "to": ip, "type": "RESOLVED_NETWORK"},
                {"from": ip, "to": f"geo_{lat}_{lon}", "type": "LOCATED_AT"},
                {"from": f"geo_{lat}_{lon}", "to": precinct_id, "type": "DISPATCHED_TO"}
            ]
        }

        # 1. Append to local Graph Export ledger
        try:
            with open(GRAPH_EXPORT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(graph_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to append triangulation telemetry to graph export: {e}")

        # 2. Push to live Neo4j if active
        if self._connected and self.driver:
            try:
                cypher = """
                MERGE (s:Suspect {id: $suspect_id})
                MERGE (h:HoneypotLink {token: $token})
                  ON CREATE SET h.created_at = $timestamp, h.layer = $layer
                  ON MATCH SET h.updated_at = $timestamp, h.layer = $layer

                MERGE (net:NetworkProfile {ip: $ip})
                  ON CREATE SET net.isp = $isp, net.fingerprint = $fp_hash, net.user_agent = $ua
                  ON MATCH SET net.isp = $isp, net.fingerprint = $fp_hash

                MERGE (geo:GeoLocation {latitude: $lat, longitude: $lon})
                  ON CREATE SET geo.city = $city, geo.region = $region, geo.accuracy_meters = $accuracy, geo.layer = $layer
                  ON MATCH SET geo.accuracy_meters = $accuracy, geo.layer = $layer

                MERGE (p:Precinct {id: $precinct_id})
                  ON CREATE SET p.name = $precinct_name

                MERGE (s)-[:TRIGGERED_HONEYPOT]->(h)
                MERGE (h)-[:RESOLVED_NETWORK]->(net)
                MERGE (net)-[:LOCATED_AT]->(geo)
                MERGE (geo)-[:DISPATCHED_TO {distance_km: $dist}]->(p)
                """
                with self.driver.session() as session:
                    session.run(cypher, {
                        "suspect_id": suspect,
                        "token": token,
                        "timestamp": timestamp,
                        "layer": layer,
                        "ip": ip,
                        "isp": isp,
                        "fp_hash": fp_hash,
                        "ua": ua or "",
                        "lat": lat,
                        "lon": lon,
                        "city": city,
                        "region": region,
                        "accuracy": accuracy,
                        "precinct_id": precinct_id,
                        "precinct_name": precinct_name,
                        "dist": dist
                    })
                print(f"[Neo4j Client] Successfully mapped triangulation graph in Neo4j for token: {token} ({layer})")
                return True
            except Exception as e:
                print(f"[-] Neo4j triangulation transaction error: {e}")
                return False

        print(f"[Neo4j Client] Triangulation ledgered to: data/raw/{GRAPH_EXPORT_FILE.name}")
        return True

    def close(self):
        if self.driver:
            self.driver.close()


# Singleton
neo4j_client = Neo4jClient()

def push_threat_to_neo4j(record: Dict[str, Any]) -> bool:
    return neo4j_client.push_threat_record(record)
