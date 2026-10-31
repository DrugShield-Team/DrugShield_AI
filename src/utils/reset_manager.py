"""
DrugShield AI - Simulation Environment Reset Manager
====================================================
Performs a deep, comprehensive reset across all subsystems:
1. SQLite Databases: Wipes runtime cases, simulation events, threat events, state transitions, dispatch logs, honeypot hits.
2. Runtime Storage: Purges event folders in data/runtime/raw/ and generated reports in data/reports/.
3. Raw Simulation Logs: Purges whatsapp_live_*, telegram_live_*, and resets raw JSON archives.
4. Microservices Memory: Calls /api/clear on WhatsApp (8090) and Telegram (8001) simulation servers.
5. In-Memory State: Clears smart buyer bot sessions and threat state machines.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("DrugShield.ResetManager")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
RUNTIME_DIR = PROJECT_ROOT / "data" / "runtime"
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"
THREAT_DB_PATH = RAW_DIR / "threat_events.db"
STORE_DB_PATH = RUNTIME_DIR / "drugshield.sqlite3"


def reset_threat_events_db() -> Dict[str, int]:
    """Wipes all rows from threat_events.db tables and vacuums."""
    deleted_counts: Dict[str, int] = {}
    if not THREAT_DB_PATH.exists():
        return deleted_counts

    tables = [
        "entity_state_machine",
        "state_transition_history",
        "honeypot_tracking_logs",
        "police_dispatch_logs",
        "suspect_cross_correlations",
        "threat_intelligence_events",
        "simulation_contacts",
    ]
    try:
        with sqlite3.connect(THREAT_DB_PATH) as conn:
            cur = conn.cursor()
            existing = {
                t[0]
                for t in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for tbl in tables:
                if tbl in existing:
                    count = cur.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]
                    cur.execute(f"DELETE FROM [{tbl}]")
                    deleted_counts[tbl] = count

            # Reset auto-increment counters
            if "sqlite_sequence" in existing:
                cur.execute(
                    "DELETE FROM sqlite_sequence WHERE name IN (%s)"
                    % ",".join(f"'{t}'" for t in tables)
                )

            # Re-seed baseline simulation targets
            cur.execute("""
            CREATE TABLE IF NOT EXISTS simulation_contacts (
                contact_id TEXT PRIMARY KEY,
                channel TEXT NOT NULL,
                name TEXT NOT NULL,
                identifier TEXT NOT NULL,
                persona TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
            now = datetime.now(timezone.utc).isoformat()
            seeds = [
                ("contact_aryan_seed", "all", "Aryan Kapoor (Dealer)", "+91 98765 43210", "TARGET_SUSPECT", "active", "{}", now, now),
                ("contact_rohit_seed", "all", "Rohit (Supplier)", "+91 98111 22334", "SUPPLIER", "active", "{}", now, now),
                ("contact_vicky_seed", "all", "Vicky (Courier Dispatch)", "+91 98222 33445", "COURIER_DISPATCH", "active", "{}", now, now),
            ]
            cur.executemany("""
            INSERT OR REPLACE INTO simulation_contacts
            (contact_id, channel, name, identifier, persona, status, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, seeds)

            conn.commit()
            cur.execute("VACUUM")
    except Exception as exc:
        logger.warning("Error resetting threat_events.db: %s", exc)

    return deleted_counts


def reset_store_db() -> Dict[str, int]:
    """Wipes all rows from drugshield.sqlite3 store tables and vacuums."""
    deleted_counts: Dict[str, int] = {}
    if not STORE_DB_PATH.exists():
        return deleted_counts

    tables = [
        "review_history",
        "evidence_cases",
        "simulation_events",
    ]
    try:
        with sqlite3.connect(STORE_DB_PATH) as conn:
            cur = conn.cursor()
            existing = {
                t[0]
                for t in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for tbl in tables:
                if tbl in existing:
                    count = cur.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]
                    cur.execute(f"DELETE FROM [{tbl}]")
                    deleted_counts[tbl] = count

            if "sqlite_sequence" in existing:
                cur.execute(
                    "DELETE FROM sqlite_sequence WHERE name IN (%s)"
                    % ",".join(f"'{t}'" for t in tables)
                )
            conn.commit()
            cur.execute("VACUUM")
    except Exception as exc:
        logger.warning("Error resetting drugshield.sqlite3: %s", exc)

    return deleted_counts


def purge_runtime_and_raw_files() -> Dict[str, int]:
    """Deletes temporary message event folders, simulation json logs, and docket exports."""
    purged: Dict[str, int] = {
        "raw_event_dirs": 0,
        "simulation_logs": 0,
        "report_files": 0,
    }

    # 1. Purge data/runtime/raw/
    runtime_raw = RUNTIME_DIR / "raw"
    if runtime_raw.exists():
        for item in runtime_raw.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    purged["raw_event_dirs"] += 1
                elif item.is_file():
                    item.unlink(missing_ok=True)
                    purged["raw_event_dirs"] += 1
            except Exception:
                pass

    # 2. Purge data/raw/ live and simulated JSON logs
    if RAW_DIR.exists():
        for item in RAW_DIR.iterdir():
            if not item.is_file():
                continue
            name = item.name.lower()
            if (
                name.startswith("whatsapp_live_")
                or name.startswith("whatsapp_simulated_")
                or name.startswith("telegram_live_")
                or name.startswith("telegram_simulated_")
                or name.endswith("_batch.json")
                or (name.startswith("test_") and name.endswith(".db"))
            ):
                try:
                    item.unlink(missing_ok=True)
                    purged["simulation_logs"] += 1
                except Exception:
                    pass

        # Reset ingested_raw_data.json and postgres_threat_records.jsonl
        master_raw = RAW_DIR / "ingested_raw_data.json"
        if master_raw.exists():
            try:
                master_raw.write_text("[]", encoding="utf-8")
            except Exception:
                pass

        postgres_threat = RAW_DIR / "postgres_threat_records.jsonl"
        if postgres_threat.exists():
            try:
                postgres_threat.write_text("", encoding="utf-8")
            except Exception:
                pass

        training_set = RAW_DIR / "training_dataset.jsonl"
        if training_set.exists():
            try:
                training_set.write_text("", encoding="utf-8")
            except Exception:
                pass

        neo4j_export = RAW_DIR / "neo4j_graph_export.jsonl"
        if neo4j_export.exists():
            try:
                neo4j_export.write_text("", encoding="utf-8")
            except Exception:
                pass

    # 3. Purge data/reports/
    if REPORTS_DIR.exists():
        for item in REPORTS_DIR.iterdir():
            try:
                if item.is_file():
                    item.unlink(missing_ok=True)
                    purged["report_files"] += 1
            except Exception:
                pass

    return purged


def reset_simulation_servers() -> Dict[str, bool]:
    """Pings running WhatsApp and Telegram node servers to clear in-memory sessions."""
    results = {"whatsapp_8090": False, "telegram_8001": False}

    # WhatsApp (8090)
    try:
        req = urllib.request.Request("http://127.0.0.1:8090/api/clear", method="POST")
        with urllib.request.urlopen(req, timeout=0.3) as resp:
            if resp.status == 200:
                results["whatsapp_8090"] = True
    except Exception:
        results["whatsapp_8090"] = False

    # Telegram (8001)
    try:
        req = urllib.request.Request("http://127.0.0.1:8001/api/clear", method="POST")
        with urllib.request.urlopen(req, timeout=0.3) as resp:
            if resp.status == 200:
                results["telegram_8001"] = True
    except Exception:
        results["telegram_8001"] = False

    return results


def perform_full_reset() -> Dict[str, Any]:
    """Orchestrates a comprehensive system reset."""
    threat_counts = reset_threat_events_db()
    store_counts = reset_store_db()
    purged_files = purge_runtime_and_raw_files()
    node_servers = reset_simulation_servers()

    # Reset in-memory smart bot sessions and caches if imported in running process
    try:
        from src.api.app import honeypot_bot
        honeypot_bot.sessions.clear()
    except Exception:
        pass

    return {
        "success": True,
        "threat_events_db": threat_counts,
        "drugshield_store_db": store_counts,
        "purged_files": purged_files,
        "simulation_nodes_cleared": node_servers,
    }
