#!/usr/bin/env python3
"""
DrugShield AI - Digital Evidence Case Report CLI Generator
==========================================================
Generates a consolidated, court-admissible forensic docket for law enforcement
officers, prosecutors, and evaluation panels.

Usage:
  python scripts/generate_case_report.py
  python scripts/generate_case_report.py latest
  python scripts/generate_case_report.py inv_test_dispatch_01
  python scripts/generate_case_report.py --token inv_57d99e2a8e5c
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.reporting.case_docket_generator import compile_case_docket, render_docket_html

def main():
    parser = argparse.ArgumentParser(
        description="DrugShield AI: Generate legal-grade digital forensic evidence case report from SQLite databases."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="latest",
        help="Tracking token (e.g. inv_...) or case/entity ID. Defaults to 'latest'.",
    )
    parser.add_argument(
        "--token",
        dest="token_opt",
        help="Explicit tracking token to filter on.",
    )
    parser.add_argument(
        "--outdir",
        default=str(PROJECT_ROOT / "data" / "reports"),
        help="Directory to save generated HTML and JSON evidence dockets.",
    )

    args = parser.parse_args()
    token = args.token_opt or args.target

    print("=" * 75)
    print("  DRUGSHIELD AI // DIGITAL EVIDENCE FORENSIC COMPILER")
    print("=" * 75)
    print(f"[*] Querying threat records for identifier: '{token}'...")

    try:
        docket = compile_case_docket(token)
    except Exception as exc:
        print(f"[-] Compilation failed: {exc}")
        sys.exit(1)

    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_token = docket["metadata"]["tracking_token"].replace("/", "_").replace("\\", "_")
    html_file = out_dir / f"forensic_docket_{safe_token}.html"
    json_file = out_dir / f"forensic_docket_{safe_token}.json"

    # Render HTML and JSON
    html_content = render_docket_html(docket)
    html_file.write_text(html_content, encoding="utf-8")
    json_file.write_text(json.dumps(docket, indent=2, ensure_ascii=False), encoding="utf-8")

    meta = docket["metadata"]
    osint = docket["osint_telemetry"]
    geo = docket["geospatial_dispatch"]
    chat = docket["chat_evidence"]

    print("\n[+] DIGITAL EVIDENCE DOCKET SUCCESSFULLY SEALED:")
    print(f"    Docket ID          : {docket['docket_id']}")
    print(f"    Primary Suspect    : {meta['target_display_name']} ({meta['channel']})")
    print(f"    Tracking Token     : {meta['tracking_token']}")
    print(f"    Chat Turns Logged  : {chat['total_messages_recorded']}")
    print(f"    Threat Threshold   : {'PASSED (Honeypot Triggered)' if chat['threat_escalation_threshold_met'] else 'MONITORING'}")
    print(f"    Source Public IP   : {osint['visitor_ip']} ({osint['city']}, {osint['country']})")
    print(f"    Assigned Precinct  : {geo['assigned_precinct_name']} ({geo['haversine_distance_km']:.2f} km)")
    print(f"    Chain-of-Custody   : SHA-256 {docket['evidence_integrity_sha256']}")
    print("\n[+] EXPORTED EVIDENCE FILES:")
    print(f"    Interactive HTML   : {html_file.resolve()}")
    print(f"    Raw JSON Evidence  : {json_file.resolve()}")
    print(f"    Live Web Route     : http://127.0.0.1:8000/api/v1/cases/{safe_token}/report")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()

