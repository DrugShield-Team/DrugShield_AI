"""
DrugShield AI - Module 1 Fast WhatsApp Ingestion Engine (whatsapp_fast.py)
========================================================================
High-speed parser and ingestion controller for the synthetic WhatsApp Web Simulator.
Reads raw payloads from `data/raw/whatsapp_simulated_*.json`, parses entities,
validates media paths for Module 2 OCR/QR forensics, and syncs data directly
into the master pipeline landing zone (`data/raw/ingested_raw_data.json`).
"""

import os
import sys
import json
import glob
from pathlib import Path
from datetime import datetime

# Path Resolution
FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent.parent
PROJECT_ROOT = SRC_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RAW_DIR = PROJECT_ROOT / "data" / "raw"
IMAGES_DIR = RAW_DIR / "images"
MASTER_INGESTED_FILE = RAW_DIR / "ingested_raw_data.json"
SRC_DATA_FILE = PROJECT_ROOT / "src" / "data.json"
ROOT_DATA_FILE = PROJECT_ROOT / "data.json"


def scan_simulated_raw_logs():
    """
    Scans data/raw/ directory for all simulated WhatsApp JSON payloads.
    Returns parsed list of unique records sorted chronologically.
    """
    if not RAW_DIR.exists():
        print(f"[-] Raw directory not found: {RAW_DIR}")
        return []

    pattern = str(RAW_DIR / "whatsapp_simulated_*.json")
    json_files = glob.glob(pattern)

    all_records = []
    seen_keys = set()

    for fpath in json_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = json.load(f)

            records = content if isinstance(content, list) else [content]
            for rec in records:
                if not isinstance(rec, dict):
                    continue

                # Deduplicate by timestamp + sender + message
                ts = rec.get("timestamp", "")
                msg = rec.get("message_body") or rec.get("text_content") or rec.get("message_text") or ""
                sender = rec.get("sender_id", "")
                key = f"{ts}_{sender}_{msg}"

                if key not in seen_keys:
                    seen_keys.add(key)
                    # Normalize fields for pipeline
                    normalized = {
                        "platform": rec.get("platform", "whatsapp_simulation"),
                        "timestamp": ts or datetime.utcnow().isoformat(),
                        "sender_id": sender,
                        "chat_id": rec.get("chat_id", "simulated_group_001"),
                        "message_body": msg,
                        "text_content": msg,
                        "message_text": msg,
                        "has_media": rec.get("has_media", False),
                        "media_path": rec.get("media_path"),
                        "extracted_upi_or_bank": rec.get("extracted_upi_or_bank") or rec.get("extracted_vpa", ""),
                        "extracted_vpa": rec.get("extracted_upi_or_bank") or rec.get("extracted_vpa", ""),
                        "is_analyst": rec.get("is_analyst", False),
                        "is_fallback_mock": False,
                        "source_file": Path(fpath).name
                    }
                    all_records.append(normalized)
        except Exception as e:
            print(f"[-] Warning: Failed to parse {fpath}: {e}")

    # Sort by timestamp
    all_records.sort(key=lambda x: x.get("timestamp", ""))
    return all_records


def sync_to_pipeline_storage(records):
    """
    Merges ingested simulated records into data/raw/ingested_raw_data.json
    and src/data.json so downstream AI modules (NLP and QR forensics) process them.
    """
    if not records:
        print("[-] No simulated WhatsApp records found in data/raw/")
        return 0

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load existing master records
    existing_records = []
    if MASTER_INGESTED_FILE.exists():
        try:
            with open(MASTER_INGESTED_FILE, "r", encoding="utf-8") as f:
                existing_records = json.load(f)
                if not isinstance(existing_records, list):
                    existing_records = []
        except Exception:
            existing_records = []

    # 2. Merge without duplicating
    existing_keys = {
        f"{r.get('timestamp')}_{r.get('sender_id')}_{r.get('message_body') or r.get('text_content') or ''}"
        for r in existing_records
    }

    new_count = 0
    for r in records:
        key = f"{r.get('timestamp')}_{r.get('sender_id')}_{r.get('message_body') or r.get('text_content') or ''}"
        if key not in existing_keys:
            existing_records.append(r)
            existing_keys.add(key)
            new_count += 1

    # 3. Write back to master files
    with open(MASTER_INGESTED_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_records, f, indent=4, ensure_ascii=False)

    if SRC_DATA_FILE.parent.exists():
        with open(SRC_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(existing_records, f, indent=4, ensure_ascii=False)

    return new_count


def run_whatsapp_fast():
    """Main entrypoint for whatsapp_fast ingestion."""
    print("==================================================================")
    print("   DRUGSHIELD AI - MODULE 1: FAST WHATSAPP SIMULATION INGESTION   ")
    print("==================================================================")

    records = scan_simulated_raw_logs()
    print(f"[*] Found {len(records)} total simulated log entries in '{RAW_DIR}'")

    if not records:
        print("[!] No simulated chat entries found. Run the simulation web app")
        print("    via 'npm start' or 'node simulator/server.js' to create logs.")
        return []

    # Calculate OSINT intelligence metrics
    suspects = set(r['sender_id'] for r in records if not r.get('is_analyst'))
    media_records = [r for r in records if r.get('has_media') and r.get('media_path')]
    financial_entities = [r['extracted_upi_or_bank'] for r in records if r.get('extracted_upi_or_bank') and r['extracted_upi_or_bank'] != 'None detected']

    print(f"\n[+] OSINT Threat Extraction Summary:")
    print(f"    - Target Suspect IDs       : {len(suspects)} unique ({', '.join(list(suspects)[:3])})")
    print(f"    - Media Evidence Files     : {len(media_records)} attachments")
    print(f"    - Financial Identifiers    : {len(financial_entities)} detected")

    new_appended = sync_to_pipeline_storage(records)
    print(f"[+] Successfully synced to master landing zone: '{MASTER_INGESTED_FILE}'")
    print(f"    - New records integrated   : {new_appended}")
    print(f"    - Total master pipeline    : {len(records)} records ready for Module 2\n")

    return records


def watch_live_crawler(interval_sec: float = 1.0):
    """
    Continuous Passive Crawler Listener:
    Monitors data/raw/ in real-time, detecting and streaming newly flagged
    simulated chat events as they arrive from the WhatsApp Web simulation.
    """
    print("==================================================================")
    print("   DRUGSHIELD AI - LIVE PASSIVE CRAWLER MONITOR (STREAMING)       ")
    print("==================================================================")
    print(f"[*] Watching landing zone : '{RAW_DIR}'")
    print("[*] Passive Mode          : Real-time threat detection active")
    print("[*] Press Ctrl+C at any time to exit\n")

    seen_files = set(glob.glob(str(RAW_DIR / "whatsapp_simulated_*.json")))
    print(f"[*] Initial state: {len(seen_files)} existing flagged raw log(s) cached.")
    print("[*] Waiting for incoming chat activity from WhatsApp simulation...\n")

    import time
    try:
        while True:
            current_files = set(glob.glob(str(RAW_DIR / "whatsapp_simulated_*.json")))
            new_files = current_files - seen_files

            if new_files:
                for fpath in sorted(new_files):
                    seen_files.add(fpath)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            rec = json.load(f)

                        now_str = datetime.now().strftime("%H:%M:%S")
                        sender = rec.get("sender_id", "Unknown")
                        msg = rec.get("message_body") or rec.get("text_content") or ""
                        media = rec.get("media_path")
                        financial = rec.get("extracted_upi_or_bank") or "None"
                        triggers = rec.get("flag_reasons") or []

                        print(f"[{now_str}] 🚨 [PASSIVE CRAWLER DETECTED SUSPICIOUS LOG]")
                        print(f"       File     : {Path(fpath).name}")
                        print(f"       Sender   : {sender}")
                        print(f"       Message  : \"{msg}\"")
                        if triggers:
                            print(f"       Triggers : {' | '.join(triggers)}")
                        if financial and financial != "None detected":
                            print(f"       Financial: {financial}")
                        if media:
                            print(f"       Media    : {media}")

                        # Sync immediately to master pipeline
                        sync_to_pipeline_storage([rec])
                        print(f"       Status   : [SYNCED TO MASTER PIPELINE -> {MASTER_INGESTED_FILE.name}]")
                        print("-" * 66)
                    except Exception as err:
                        print(f"[-] Error reading new log {fpath}: {err}")

            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("\n[*] Live Passive Crawler Monitor stopped by user.")


def scrape_whatsapp_feed(use_mock: bool = True, live_invite_urls: list = None, limit: int = 6):
    """Pipeline entrypoint alias for main.py integration."""
    return run_whatsapp_fast()[:limit]

main = run_whatsapp_fast
run = run_whatsapp_fast

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--watch", "-w", "--live", "watch"):
        watch_live_crawler()
    else:
        run_whatsapp_fast()
