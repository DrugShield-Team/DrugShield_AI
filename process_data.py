# process_data.py
import json
import logging
from pathlib import Path
from src.ai_pipeline.message_analyzer import analyze_message
from src.ai_pipeline.nlp_classifier import HinglishSlangDetector

logger = logging.getLogger("DrugShield.ProcessData")


def process_raw_data():
    """
    Unified Data Processing Pipeline:
    Enriches ingested records with text analysis and QR/VPA evidence extraction.
    """
    raw_file = Path("data/raw/ingested_raw_data.json")
    raw_dir = Path("data/raw")
    images_dir = raw_dir / "images"
    processed_dir = Path("data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)

    if not raw_file.exists():
        print(f"Error: {raw_file} not found. Run main.py first!")
        return []

    print(f"Loading raw data from {raw_file}...")
    try:
        with open(raw_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {raw_file}: {e}")
        data = []

    detector = HinglishSlangDetector()
    print("Executing per-message NLP, QR decoding, and VPA candidate extraction...")

    for item in data:
        item["processed"] = True

        # Resolve the message's optional image attachment before per-message
        # analysis. The analyzer handles text, QR payloads, and VPA candidates.
        text_content = item.get("text_content") or item.get("text") or item.get("message_text") or item.get("message") or ""
        media_path = item.get("media_path")
        resolved_img = None
        if media_path:
            candidate_paths = [
                Path(media_path),
                raw_dir / Path(media_path).name,
                images_dir / Path(media_path).name,
            ]
            resolved_img = next((p for p in candidate_paths if p.is_file()), None)

        result = analyze_message(
            text_content,
            [resolved_img] if resolved_img else [],
            text_detector=detector,
        )
        analysis = result["text_analysis"]
        item["nlp_analysis"] = {
            "normalized_text": analysis["normalized_text"],
            "detected_slangs": analysis["detected_slangs"],
            "risk_score": analysis["risk_score"],
            "is_suspicious": analysis["is_suspicious"],
        }
        item["qr_scans"] = result["qr_scans"]
        if result["qr_scans"]:
            # Retain the old singular field for existing report consumers.
            item["qr_scan"] = result["qr_scans"][0]
        item["vpa_candidates"] = result["vpa_candidates"]

        # QR payloads and VPA candidates are evidence only. They do not set
        # message risk by themselves; the current threshold uses text analysis.
        nlp_risk = analysis["risk_score"]
        current_risk = item.get("risk_score", 0.0)
        item["risk_score"] = round(max(current_risk, nlp_risk), 2)
        if "high_risk" not in item:
            item["high_risk"] = item["risk_score"] > 0.40 or analysis["is_suspicious"]

    output_file = processed_dir / "processed_data.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"Data successfully processed and saved to: {output_file}")
    return data


# Pipeline alias for compatibility
def process_ingested_messages():
    return process_raw_data()


if __name__ == "__main__":
    process_raw_data()
