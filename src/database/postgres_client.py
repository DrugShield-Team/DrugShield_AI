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
        """
        with self._pg_conn.cursor() as cur:
            cur.execute(query)

    def push_threat_record(self, record: Dict[str, Any]) -> bool:
        """Inserts a threat intelligence record into PostgreSQL or fallback store."""
        msg_id = record.get("id") or f"evt_{Date_now()}"
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
                print(f"[PostgreSQL Client] 🟢 Threat event persisted to PostgreSQL: {msg_id}")
                return True
            except Exception as e:
                print(f"[-] PostgreSQL insert error: {e}")
                return False

        print(f"[PostgreSQL Client] 📁 Threat event stored in SQLite: data/raw/{SQLITE_DB_PATH.name}")
        return True


postgres_client = PostgresClient()

def push_threat_to_postgres(record: Dict[str, Any]) -> bool:
    return postgres_client.push_threat_record(record)
