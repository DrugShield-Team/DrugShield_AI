"""
DrugShield AI - Threat Accumulator & Threshold State Machine
============================================================
Tracks threat accumulation per chat entity / thread across Hinglish slang,
OCR pill detection, and QR payloads. When 4-5 consecutive flag events accumulate,
transitions status from PASSIVE_MONITOR to BOT_ENGAGED / ACTIVE_HONEYPOT_READY
and triggers handoff to the Smart Buyer Bot persona while pausing crawler loops.
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
STATE_BOT_ENGAGED = "BOT_ENGAGED"
STATE_HONEYPOT_ENGAGED = "HONEYPOT_ENGAGED"
STATE_INVOICE_SENT = "INVOICE_SENT"
STATE_TARGET_GEO_LOCATED = "TARGET_GEO_LOCATED"
STATE_DISPATCH_INITIATED = "DISPATCH_INITIATED"

# Strict 4-5 message consecutive threat threshold
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
        Evaluate an incoming threat record from a suspect.
        Strictly requires 4 to 5 consecutive flagged messages from the dealer
        before transitioning to BOT_ENGAGED / ACTIVE_HONEYPOT_READY.
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
                existing_count = row["flag_count"] or 0

                # Consecutive tracking: increment if flagged, else reset if innocent non-flagged message
                if is_flagged:
                    current_count = existing_count + 1
                else:
                    # Non-threat message in monitor state resets consecutive count
                    current_count = existing_count if prev_state != STATE_PASSIVE_MONITOR else 0

                highest_score = max(float(row["highest_threat_score"] or 0.0), score)

                try:
                    existing_reasons = json.loads(row["flag_reasons"] or "[]")
                except Exception:
                    existing_reasons = []
                merged_reasons = list(dict.fromkeys(existing_reasons + reasons))

                # Strictly wait until 4 to 5 consecutive flagged messages accumulate
                if current_count >= THRESHOLD_FLAG_COUNT and prev_state in (STATE_PASSIVE_MONITOR, "IDLE"):
                    current_state = STATE_ACTIVE_HONEYPOT_READY
                    crawler_paused = 1
                    self.pause_thread(chat_id)
                    self.pause_thread(entity_id)
                else:
                    current_state = prev_state
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

            # Record transition history if state advanced
            if current_state != prev_state:
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
                        f"Threshold reached ({current_count} consecutive flagged messages)",
                        json.dumps(reasons),
                        now,
                    ),
                )

            conn.commit()

        threshold_reached = bool(current_count >= THRESHOLD_FLAG_COUNT and current_state == STATE_ACTIVE_HONEYPOT_READY)

        return {
            "entity_id": entity_id,
            "previous_state": prev_state,
            "current_state": current_state,
            "flag_count": current_count,
            "threshold_required": THRESHOLD_FLAG_COUNT,
            "threshold_reached": threshold_reached,
            "is_flagged": is_flagged,
            "crawler_paused": bool(self.is_thread_paused(chat_id)),
            "reasons": reasons,
            "updated_at": now,
        }

    def register_entity(
        self,
        entity_id: str,
        initial_state: str = STATE_PASSIVE_MONITOR,
        persona: Optional[str] = None,
        display_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Dynamically register an entity into the state machine.
        Allows adding new simulation targets without hardcoded limitations.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT current_state, flag_count, highest_threat_score FROM entity_state_machine WHERE entity_id = ?", (entity_id,))
            row = cur.fetchone()
            reasons = [f"Registered as {persona or initial_state}"]
            if display_name:
                reasons.append(f"Alias: {display_name}")

            if not row:
                cur.execute(
                    """
                    INSERT INTO entity_state_machine
                    (entity_id, current_state, flag_count, highest_threat_score, flag_reasons, crawler_paused, created_at, updated_at)
                    VALUES (?, ?, 0, 0.0, ?, 0, ?, ?)
                    """,
                    (entity_id, initial_state, json.dumps(reasons), now, now),
                )
                cur.execute(
                    """
                    INSERT INTO state_transition_history
                    (entity_id, previous_state, new_state, trigger_reason, details, timestamp)
                    VALUES (?, 'UNINITIALIZED', ?, 'Dynamic contact ingestion', ?, ?)
                    """,
                    (entity_id, initial_state, json.dumps(metadata or {}), now),
                )
            else:
                cur.execute(
                    """
                    UPDATE entity_state_machine
                    SET updated_at = ?
                    WHERE entity_id = ?
                    """,
                    (now, entity_id),
                )
            conn.commit()

        logger.info(f"[State Machine] Registered entity '{entity_id}' as {persona or initial_state}")
        return self.get_entity_state(entity_id)

    def transition_state(
        self,
        entity_id: str,
        new_state: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Explicitly transition an entity to a new operational state."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT current_state FROM entity_state_machine WHERE entity_id = ?", (entity_id,))
            row = cur.fetchone()
            prev_state = row["current_state"] if row else "UNINITIALIZED"

            cur.execute(
                """
                INSERT INTO entity_state_machine (entity_id, current_state, flag_count, highest_threat_score, flag_reasons, crawler_paused, created_at, updated_at)
                VALUES (?, ?, 0, 0.0, '[]', 0, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    current_state = excluded.current_state,
                    updated_at = excluded.updated_at
                """,
                (entity_id, new_state, now, now),
            )

            cur.execute(
                """
                INSERT INTO state_transition_history
                (entity_id, previous_state, new_state, trigger_reason, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (entity_id, prev_state, new_state, reason, json.dumps(details or {}), now),
            )
            conn.commit()

        logger.info(f"[State Transition] Entity: '{entity_id}' -> {new_state} (Reason: {reason})")
        return True

    def get_entity_state(self, entity_id: str) -> Dict[str, Any]:
        """Fetch current state machine position for an entity."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM entity_state_machine WHERE entity_id = ?", (entity_id,))
            row = cur.fetchone()
            if not row:
                return {
                    "entity_id": entity_id,
                    "current_state": STATE_PASSIVE_MONITOR,
                    "flag_count": 0,
                    "highest_threat_score": 0.0,
                    "crawler_paused": False,
                }
            return {
                "entity_id": row["entity_id"],
                "current_state": row["current_state"],
                "flag_count": row["flag_count"],
                "highest_threat_score": row["highest_threat_score"],
                "flag_reasons": json.loads(row["flag_reasons"] or "[]"),
                "crawler_paused": bool(row["crawler_paused"]),
                "updated_at": row["updated_at"],
            }

    def pause_thread(self, thread_id: str) -> None:
        """Pause automated scraping/ingestion for this thread."""
        _PAUSED_THREADS.add(str(thread_id))
        logger.info(f"[Crawler Engine] Thread {thread_id} paused due to honeypot transition.")

    def resume_thread(self, thread_id: str) -> None:
        """Resume thread scraping."""
        _PAUSED_THREADS.discard(str(thread_id))

    def is_thread_paused(self, thread_id: str) -> bool:
        """Check if an ingestion thread is currently locked for honeypot operation."""
        return str(thread_id) in _PAUSED_THREADS


state_machine = ThreatStateMachine()
