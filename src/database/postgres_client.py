"""
DrugShield AI - Module 4: PostgreSQL Database Client (postgres_client.py)
========================================================================
Stores structured threat intelligence records and event telemetry:
- Table: `threat_intelligence_events`
- Columns: id, platform, timestamp, sender_id, message_text, threat_score,
           flagged_status, upi_ids, bank_accounts, detected_drugs, media_path
Maintains local SQLite fallback at `data/raw/threat_events.db` and JSONL archive
if PostgreSQL server is offline.
"""

import os
import json
import sqlite3
import time
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
SQLITE_DB_PATH = RAW_DIR / "threat_events.db"
POSTGRES_ARCHIVE_FILE = RAW_DIR / "postgres_threat_records.jsonl"

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "drugshield_osint")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DATABASE_URL = os.getenv("DATABASE_URL")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None


class PostgresClient:
    def __init__(self):
        self._pg_conn = None
        self._connected = False
        self._init_sqlite_fallback()

        if psycopg2 is not None:
            try:
                if DATABASE_URL:
                    self._pg_conn = psycopg2.connect(DATABASE_URL)
                else:
                    self._pg_conn = psycopg2.connect(
                        host=POSTGRES_HOST,
                        port=POSTGRES_PORT,
                        dbname=POSTGRES_DB,
                        user=POSTGRES_USER,
                        password=POSTGRES_PASSWORD,
                        connect_timeout=3
                    )
                self._pg_conn.autocommit = True
                self._create_pg_tables()
                self._connected = True
                print(f"[PostgreSQL Client] Connected to database '{POSTGRES_DB}'")
            except Exception as e:
                self._connected = False
                print(f"[PostgreSQL Notice] PostgreSQL server offline. Using SQLite fallback: {SQLITE_DB_PATH.name}")
        else:
            print(f"[PostgreSQL Notice] 'psycopg2' library not installed. Using SQLite fallback: {SQLITE_DB_PATH.name}")

    def _init_sqlite_fallback(self):
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(SQLITE_DB_PATH) as conn:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS threat_intelligence_events (
                    id TEXT PRIMARY KEY,
                    platform TEXT,
                    timestamp TEXT,
                    sender_id TEXT,
                    message_text TEXT,
                    threat_score REAL,
                    flagged_status INTEGER,
                    upi_ids TEXT,
                    bank_accounts TEXT,
                    detected_drugs TEXT,
                    media_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS honeypot_tracking_logs (
                    id TEXT PRIMARY KEY,
                    tracking_token TEXT,
                    ip TEXT,
                    is_simulated INTEGER,
                    country TEXT,
                    region TEXT,
                    city TEXT,
                    latitude REAL,
                    longitude REAL,
                    isp TEXT,
                    fingerprint_hash TEXT,
                    user_agent TEXT,
                    accept_language TEXT,
                    heuristics TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS police_dispatch_logs (
                    id TEXT PRIMARY KEY,
                    tracking_token TEXT,
                    target_lat REAL,
                    target_lon REAL,
                    precinct_id TEXT,
                    precinct_name TEXT,
                    distance_km REAL,
                    eta_minutes INTEGER,
                    dispatch_status TEXT,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
        except Exception as e:
            print(f"[-] SQLite initialization error: {e}")

    def _create_pg_tables(self):
        if not self._pg_conn:
            return
        query = """
        CREATE TABLE IF NOT EXISTS threat_intelligence_events (
            id VARCHAR(128) PRIMARY KEY,
            platform VARCHAR(64),
            timestamp VARCHAR(64),
            sender_id VARCHAR(128),
            message_text TEXT,
            threat_score NUMERIC(4, 2),
            flagged_status BOOLEAN,
            upi_ids TEXT,
            bank_accounts TEXT,
            detected_drugs TEXT,
            media_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS honeypot_tracking_logs (
            id VARCHAR(128) PRIMARY KEY,
            tracking_token VARCHAR(128),
            ip VARCHAR(64),
            is_simulated BOOLEAN,
            country VARCHAR(64),
            region VARCHAR(64),
            city VARCHAR(64),
            latitude NUMERIC(10, 6),
            longitude NUMERIC(10, 6),
            isp VARCHAR(128),
            fingerprint_hash VARCHAR(128),
            user_agent TEXT,
            accept_language VARCHAR(128),
            heuristics TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS police_dispatch_logs (
            id VARCHAR(128) PRIMARY KEY,
            tracking_token VARCHAR(128),
            target_lat NUMERIC(10, 6),
            target_lon NUMERIC(10, 6),
            precinct_id VARCHAR(64),
            precinct_name VARCHAR(128),
            distance_km NUMERIC(8, 2),
            eta_minutes INTEGER,
            dispatch_status VARCHAR(64),
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        with self._pg_conn.cursor() as cur:
            cur.execute(query)

    def push_threat_record(self, record: Dict[str, Any]) -> bool:
        """Inserts a threat intelligence record into PostgreSQL or fallback store."""
        msg_id = record.get("id") or f"evt_{int(datetime.utcnow().timestamp()*1000)}"
        platform = record.get("platform", "unknown")
        timestamp = record.get("timestamp", "")
        sender = record.get("sender_id") or record.get("sender_username") or "unknown"
        content = record.get("message_text") or record.get("message_body") or ""
        score = float(record.get("threat_score") or record.get("risk_score") or 0.0)
        flagged = 1 if (record.get("flagged_status") or record.get("isFlagged") or score >= 0.60) else 0

        entities = record.get("extracted_entities", {})
        upis_str = json.dumps(entities.get("upi_ids", []))
        banks_str = json.dumps(entities.get("bank_accounts", []))
        drugs_str = json.dumps(entities.get("narcotics_detected", []))
        media_path = record.get("media_path") or ""

        # 1. Archive to JSONL
        try:
            with open(POSTGRES_ARCHIVE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass

        # 2. Store in SQLite
        try:
            with sqlite3.connect(SQLITE_DB_PATH) as conn:
                conn.execute("""
                INSERT OR REPLACE INTO threat_intelligence_events
                (id, platform, timestamp, sender_id, message_text, threat_score, flagged_status, upi_ids, bank_accounts, detected_drugs, media_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (msg_id, platform, timestamp, sender, content, score, flagged, upis_str, banks_str, drugs_str, media_path))
        except Exception as e:
            print(f"[-] SQLite insert error: {e}")

        # 3. Store in PostgreSQL if connected
        if self._connected and self._pg_conn:
            try:
                with self._pg_conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO threat_intelligence_events
                    (id, platform, timestamp, sender_id, message_text, threat_score, flagged_status, upi_ids, bank_accounts, detected_drugs, media_path)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                      threat_score = EXCLUDED.threat_score,
                      flagged_status = EXCLUDED.flagged_status
                    """, (msg_id, platform, timestamp, sender, content, score, bool(flagged), upis_str, banks_str, drugs_str, media_path))
                print(f"[PostgreSQL Client] [PostgreSQL] Threat event persisted: {msg_id}")
                return True
            except Exception as e:
                print(f"[-] PostgreSQL insert error: {e}")
                return False

        print(f"[PostgreSQL Client] [SQLite] Threat event stored: data/raw/{SQLITE_DB_PATH.name}")
        return True

    def record_honeypot_hit(self, hit_data: Dict[str, Any]) -> str:
        """Securely commit a captured honeypot visitor event to audit logs."""
        hit_id = hit_data.get("id") or f"hit_{int(time.time()*1000)}"
        token = hit_data.get("tracking_token", "")
        ip = hit_data.get("ip", "127.0.0.1")
        is_sim = 1 if hit_data.get("is_simulated", True) else 0
        country = hit_data.get("country", "")
        region = hit_data.get("region", "")
        city = hit_data.get("city", "")
        lat = float(hit_data.get("latitude") or 0.0)
        lon = float(hit_data.get("longitude") or 0.0)
        isp = hit_data.get("isp", "")
        fp_hash = hit_data.get("fingerprint_hash", "")
        ua = hit_data.get("user_agent", "")
        lang = hit_data.get("accept_language", "")
        heuristics_str = json.dumps(hit_data.get("heuristics") or {})

        try:
            with sqlite3.connect(SQLITE_DB_PATH) as conn:
                conn.execute("""
                INSERT OR REPLACE INTO honeypot_tracking_logs
                (id, tracking_token, ip, is_simulated, country, region, city, latitude, longitude, isp, fingerprint_hash, user_agent, accept_language, heuristics)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (hit_id, token, ip, is_sim, country, region, city, lat, lon, isp, fp_hash, ua, lang, heuristics_str))
        except Exception as e:
            print(f"[-] Failed to record honeypot hit in SQLite: {e}")

        if self._connected and self._pg_conn:
            try:
                with self._pg_conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO honeypot_tracking_logs
                    (id, tracking_token, ip, is_simulated, country, region, city, latitude, longitude, isp, fingerprint_hash, user_agent, accept_language, heuristics)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (hit_id, token, ip, bool(is_sim), country, region, city, lat, lon, isp, fp_hash, ua, lang, heuristics_str))
            except Exception as e:
                print(f"[-] Failed to record honeypot hit in PostgreSQL: {e}")

        return hit_id

    def record_dispatch_alert(self, alert: Dict[str, Any]) -> str:
        """Securely commit an assigned police precinct dispatch alert."""
        alert_id = alert.get("id") or f"disp_{int(time.time()*1000)}"
        token = alert.get("tracking_token", "")
        coords = alert.get("target_coordinates") or {}
        lat = float(coords.get("latitude") or 0.0)
        lon = float(coords.get("longitude") or 0.0)
        assigned = alert.get("assigned_precinct") or {}
        p_id = assigned.get("precinct_id", "")
        p_name = assigned.get("name", "")
        dist = float(assigned.get("distance_km") or 0.0)
        eta = int(assigned.get("estimated_eta_minutes") or 0)
        status = alert.get("dispatch_status", "DISPATCH_RECOMMENDED")
        details = json.dumps(alert)

        try:
            with sqlite3.connect(SQLITE_DB_PATH) as conn:
                conn.execute("""
                INSERT OR REPLACE INTO police_dispatch_logs
                (id, tracking_token, target_lat, target_lon, precinct_id, precinct_name, distance_km, eta_minutes, dispatch_status, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (alert_id, token, lat, lon, p_id, p_name, dist, eta, status, details))
        except Exception as e:
            print(f"[-] Failed to record dispatch alert in SQLite: {e}")

        if self._connected and self._pg_conn:
            try:
                with self._pg_conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO police_dispatch_logs
                    (id, tracking_token, target_lat, target_lon, precinct_id, precinct_name, distance_km, eta_minutes, dispatch_status, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (alert_id, token, lat, lon, p_id, p_name, dist, eta, status, details))
            except Exception as e:
                print(f"[-] Failed to record dispatch alert in PostgreSQL: {e}")

        return alert_id

    def get_recent_dispatch_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent police dispatch events."""
        results = []
        try:
            with sqlite3.connect(SQLITE_DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM police_dispatch_logs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
                for r in rows:
                    item = dict(r)
                    try:
                        item["details"] = json.loads(item.get("details") or "{}")
                    except Exception:
                        pass
                    results.append(item)
        except Exception as e:
            print(f"[-] Error querying dispatch alerts: {e}")
        return results

    def get_recent_honeypot_hits(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent captured honeypot hits."""
        results = []
        try:
            with sqlite3.connect(SQLITE_DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM honeypot_tracking_logs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
                for r in rows:
                    item = dict(r)
                    try:
                        item["heuristics"] = json.loads(item.get("heuristics") or "{}")
                    except Exception:
                        pass
                    results.append(item)
        except Exception as e:
            print(f"[-] Error querying honeypot hits: {e}")
        return results


postgres_client = PostgresClient()

def push_threat_to_postgres(record: Dict[str, Any]) -> bool:
    return postgres_client.push_threat_record(record)
