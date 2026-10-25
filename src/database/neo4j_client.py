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
                print(f"[Neo4j Client] 🟢 Successfully mapped threat graph in Neo4j: {msg_id}")
                return True
            except Exception as e:
                print(f"[-] Neo4j transaction error: {e}")
                return False

        print(f"[Neo4j Client] 📁 Graph Transaction ledgered to: data/raw/{GRAPH_EXPORT_FILE.name}")
        return True

    def close(self):
        if self.driver:
            self.driver.close()


# Singleton
neo4j_client = Neo4jClient()

def push_threat_to_neo4j(record: Dict[str, Any]) -> bool:
    return neo4j_client.push_threat_record(record)
