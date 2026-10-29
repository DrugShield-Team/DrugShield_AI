"""
DrugShield AI - Threat Accumulator & Threshold State Machine
============================================================
Tracks threat accumulation per chat entity / thread across Hinglish slang,
OCR pill detection, and QR payloads. When 4-5 flag events accumulate,
transitions status from PASSIVE_MONITOR to ACTIVE_HONEYPOT_READY and triggers
handoff to the Smart Buyer Bot persona while pausing crawler loops for that thread.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
STATE_DB_PATH = RAW_DIR / "threat_events.db"

logger = logging.getLogger("DrugShield.StateMachine")

# State constants
STATE_PASSIVE_MONITOR = "PASSIVE_MONITOR"
STATE_ACTIVE_HONEYPOT_READY = "ACTIVE_HONEYPOT_READY"
STATE_HONEYPOT_ENGAGED = "HONEYPOT_ENGAGED"
STATE_INVOICE_SENT = "INVOICE_SENT"
STATE_TARGET_GEO_LOCATED = "TARGET_GEO_LOCATED"
STATE_DISPATCH_INITIATED = "DISPATCH_INITIATED"

THRESHOLD_FLAG_COUNT = 4

# In-memory paused crawler thread registry
_PAUSED_THREADS: Set[str] = set()


class ThreatStateMachine:
    """
    State machine that monitors entity threat progression and manages crawler handoff.
    """

    def __init__(self, db_path: Path = STATE_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS entity_state_machine (
                    entity_id TEXT PRIMARY KEY,
                    current_state TEXT NOT NULL,
                    flag_count INTEGER DEFAULT 0,
                    highest_threat_score REAL DEFAULT 0.0,
                    flag_reasons TEXT,
                    crawler_paused INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS state_transition_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    previous_state TEXT NOT NULL,
                    new_state TEXT NOT NULL,
                    trigger_reason TEXT,
                    details TEXT,
                    timestamp TEXT NOT NULL
                )
                """)
        except Exception as e:
            logger.error(f"Failed to initialize state machine tables: {e}")

    def evaluate_threat_event(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate an incoming threat record. If flagged, increments the entity's
        flag accumulator. If flag count reaches THRESHOLD_FLAG_COUNT (4-5),
        automatically transitions state to ACTIVE_HONEYPOT_READY and pauses the thread.
        """
        entity_id = (
            record.get("sender_id")
            or record.get("sender_username")
            or record.get("chat_id")
            or "unknown_target"
        )
        chat_id = record.get("chat_id") or entity_id
        score = float(record.get("threat_score") or record.get("risk_score") or 0.0)
        is_flagged = bool(record.get("flagged_status") or record.get("isFlagged") or score >= 0.60)

        # Detect specific flag categories
        substances = record.get("extracted_entities", {}).get("narcotics_detected", [])
        ocr_performed = record.get("ocr_forensics", {}).get("text_extracted", False)
        qr_detected = record.get("qr_scan", {}).get("qr_detected", False)
        solicitation = record.get("nlp_analysis", {}).get("solicitation_intent", False)

        reasons = []
        if substances:
            reasons.append(f"Substances: {', '.join(substances[:3])}")
        if ocr_performed:
            reasons.append("OCR Media Match")
        if qr_detected:
            reasons.append("Decoded QR Payload")
        if solicitation:
            reasons.append("Solicitation Pattern")
        if score >= 0.60:
            reasons.append(f"High Threat Score ({score:.2f})")

        now = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM entity_state_machine WHERE entity_id = ?", (entity_id,))
            row = cur.fetchone()

            if not row:
                initial_count = 1 if is_flagged else 0
                state = STATE_PASSIVE_MONITOR
                if initial_count >= THRESHOLD_FLAG_COUNT:
                    state = STATE_ACTIVE_HONEYPOT_READY

                cur.execute(
                    """
                    INSERT INTO entity_state_machine
                    (entity_id, current_state, flag_count, highest_threat_score, flag_reasons, crawler_paused, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity_id,
                        state,
                        initial_count,
                        score,
                        json.dumps(reasons),
                        1 if state == STATE_ACTIVE_HONEYPOT_READY else 0,
                        now,
                        now,
                    ),
                )
                current_count = initial_count
                prev_state = STATE_PASSIVE_MONITOR
                current_state = state
            else:
                prev_state = row["current_state"]
                current_count = row["flag_count"] + (1 if is_flagged else 0)
                highest_score = max(float(row["highest_threat_score"] or 0.0), score)

                # Parse existing reasons and merge
                try:
                    existing_reasons = json.loads(row["flag_reasons"] or "[]")
                except Exception:
                    existing_reasons = []
                merged_reasons = list(dict.fromkeys(existing_reasons + reasons))

                # Check threshold transition
                # Trigger when flag count hits threshold (either reaching 4 from monitor, or every threshold cycle)
                if current_count >= THRESHOLD_FLAG_COUNT:
                    current_state = STATE_ACTIVE_HONEYPOT_READY
                    crawler_paused = 1
                    # Reset count cycle for subsequent honeypot re-engagements
                    current_count = 0
                    self.pause_thread(chat_id)
                    self.pause_thread(entity_id)
                else:
                    current_state = prev_state if prev_state != STATE_ACTIVE_HONEYPOT_READY else STATE_PASSIVE_MONITOR
                    crawler_paused = row["crawler_paused"]

                cur.execute(
                    """
                    UPDATE entity_state_machine
                    SET current_state = ?, flag_count = ?, highest_threat_score = ?,
                        flag_reasons = ?, crawler_paused = ?, updated_at = ?
                    WHERE entity_id = ?
                    """,
                    (
                        current_state,
                        current_count,
                        highest_score,
                        json.dumps(merged_reasons),
                        crawler_paused,
                        now,
                        entity_id,
                    ),
                )

            # Record transition if state changed
            if prev_state != current_state:
                cur.execute(
                    """
                    INSERT INTO state_transition_history
                    (entity_id, previous_state, new_state, trigger_reason, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity_id,
                        prev_state,
                        current_state,
                        f"Accumulated {current_count} flags (Threshold: {THRESHOLD_FLAG_COUNT})",
                        json.dumps({"reasons": reasons, "score": score, "chat_id": chat_id}),
                        now,
                    ),
                )

        return {
            "entity_id": entity_id,
            "chat_id": chat_id,
            "previous_state": prev_state,
            "current_state": current_state,
            "flag_count": current_count,
            "threshold_reached": current_count >= THRESHOLD_FLAG_COUNT,
            "crawler_paused": self.is_thread_paused(chat_id),
            "state_changed": prev_state != current_state,
        }

    def transition_state(
        self,
        entity_id: str,
        new_state: str,
        reason: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Manually or programmatically advance state for an entity."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT current_state FROM entity_state_machine WHERE entity_id = ?", (entity_id,))
            row = cur.fetchone()
            prev_state = row["current_state"] if row else STATE_PASSIVE_MONITOR

            cur.execute(
                """
                INSERT INTO entity_state_machine (entity_id, current_state, flag_count, created_at, updated_at)
                VALUES (?, ?, 0, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET current_state = ?, updated_at = ?
                """,
                (entity_id, new_state, now, now, new_state, now),
            )
            cur.execute(
                """
                INSERT INTO state_transition_history
                (entity_id, previous_state, new_state, trigger_reason, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (entity_id, prev_state, new_state, reason, json.dumps(details or {}), now),
            )

        return {
            "entity_id": entity_id,
            "previous_state": prev_state,
            "new_state": new_state,
            "timestamp": now,
        }

    def get_entity_state(self, entity_id: str) -> Dict[str, Any]:
        """Retrieve current state and flag telemetry for an entity."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM entity_state_machine WHERE entity_id = ?", (entity_id,))
            row = cur.fetchone()
            if not row:
                return {
                    "entity_id": entity_id,
                    "current_state": STATE_PASSIVE_MONITOR,
                    "flag_count": 0,
                    "crawler_paused": False,
                }
            return {
                "entity_id": row["entity_id"],
                "current_state": row["current_state"],
                "flag_count": row["flag_count"],
                "highest_threat_score": row["highest_threat_score"],
                "reasons": json.loads(row["flag_reasons"] or "[]"),
                "crawler_paused": bool(row["crawler_paused"]),
                "updated_at": row["updated_at"],
            }


    def reset_entity(self, entity_id: str) -> None:
        """Reset flag count and state back to PASSIVE_MONITOR for testing/demo runs."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE entity_state_machine
                SET current_state = ?, flag_count = 0, highest_threat_score = 0.0, crawler_paused = 0, updated_at = ?
                WHERE entity_id = ?
                """,
                (STATE_PASSIVE_MONITOR, now, entity_id),
            )
        self.resume_thread(entity_id)

    @staticmethod
    def pause_thread(thread_id: str):
        """Register a thread or entity as paused in memory."""
        if thread_id:
            _PAUSED_THREADS.add(str(thread_id).strip())

    @staticmethod
    def resume_thread(thread_id: str):
        """Unpause a thread in memory."""
        if thread_id:
            _PAUSED_THREADS.discard(str(thread_id).strip())

    @staticmethod
    def is_thread_paused(thread_id: str) -> bool:
        """Check if ingestion is currently paused for this thread."""
        return str(thread_id).strip() in _PAUSED_THREADS


# Global singleton
state_machine = ThreatStateMachine()
