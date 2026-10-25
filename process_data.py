# process_data.py
"""
DrugShield AI - Unified Data Processing Pipeline
================================================
Processes ingested raw records, executes Hinglish NLP slang analysis,
QR & OCR forensics, financial entity extraction, and updates processed_data.json.
"""

import json
import logging
from pathlib import Path
from src.ai_pipeline.threat_pipeline import evaluate_live_message_threat

logger = logging.getLogger("DrugShield.ProcessData")


def process_raw_data():
    raw_file = Path("data/raw/ingested_raw_data.json")
    processed_dir = Path("data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)

    if not raw_file.exists():
        print(f"Error: {raw_file} not found. Run main.py first!")
        return []

    print(f"Loading raw data from {raw_file}...")
    try:
        with open(raw_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                data = [data] if isinstance(data, dict) else []
    except Exception as e:
        print(f"Error reading {raw_file}: {e}")
        data = []

    print(f"Executing active threat evaluation on {len(data)} raw record(s)...")
    processed_records = []
    for item in data:
        if isinstance(item, dict):
            enriched = evaluate_live_message_threat(item)
            enriched["processed"] = True
            processed_records.append(enriched)

    output_file = processed_dir / "processed_data.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(processed_records, f, indent=4, ensure_ascii=False)

    print(f"Data successfully processed and saved to: {output_file}")
    return processed_records


def process_ingested_messages():
    return process_raw_data()


if __name__ == "__main__":
    process_raw_data()
