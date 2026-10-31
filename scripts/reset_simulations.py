#!/usr/bin/env python3
"""
DrugShield AI - Simulation Reset Utility
========================================
Purges all runtime databases, active honeypots, conversation dockets,
and chat message logs across all 3 platforms (WhatsApp, Telegram, Instagram).

Usage:
    python scripts/reset_simulations.py
    npm run reset
"""

import json
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.reset_manager import perform_full_reset


def main():
    print("=" * 70)
    print("  DRUGSHIELD AI // SIMULATION ENVIRONMENT PURGE & RESET")
    print("=" * 70)
    print("[*] Initiating comprehensive reset across all subsystems...")

    result = perform_full_reset()

    # Threat Events DB
    print("\n[1] Threat Intelligence & Geolocation Database (threat_events.db):")
    threat_db = result.get("threat_events_db", {})
    if threat_db:
        for tbl, count in threat_db.items():
            print(f"    - Wiped table [{tbl}]: {count} records removed")
    else:
        print("    - Clean (0 existing records)")

    # DrugShield Store DB
    print("\n[2] Evidence Store Database (drugshield.sqlite3):")
    store_db = result.get("drugshield_store_db", {})
    if store_db:
        for tbl, count in store_db.items():
            print(f"    - Wiped table [{tbl}]: {count} records removed")
    else:
        print("    - Clean (0 existing records)")

    # Runtime & Raw Files
    print("\n[3] File System Runtime Artifacts & Logs:")
    purged = result.get("purged_files", {})
    print(f"    - Purged raw message event folders : {purged.get('raw_event_dirs', 0)} directories")
    print(f"    - Purged simulation JSON log files : {purged.get('simulation_logs', 0)} files")
    print(f"    - Purged forensic docket exports   : {purged.get('report_files', 0)} files")

    # Simulation Microservices
    print("\n[4] Microservice Node Memory Resets:")
    nodes = result.get("simulation_nodes_cleared", {})
    wa_status = "[ONLINE & CLEARED]" if nodes.get("whatsapp_8090") else "[OFFLINE / NO ACTIVE RUNTIME]"
    tg_status = "[ONLINE & CLEARED]" if nodes.get("telegram_8001") else "[OFFLINE / NO ACTIVE RUNTIME]"
    print(f"    - WhatsApp Simulation Server (8090) : {wa_status}")
    print(f"    - Telegram Simulation Server (8001) : {tg_status}")

    print("\n" + "=" * 70)
    print("  [SUCCESS] All chat history, threat state, and dockets reset to zero!")
    print("  Ready for a 100% fresh demonstration.")
    print("=" * 70)


if __name__ == "__main__":
    main()

