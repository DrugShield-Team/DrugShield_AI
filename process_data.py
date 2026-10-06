# process_data.py
import json
import logging
from pathlib import Path
from src.ai_pipeline.nlp_classifier import HinglishSlangDetector
from src.ai_pipeline.qr_detector import scan_qr_payload

logger = logging.getLogger("DrugShield.ProcessData")


def process_raw_data():
    """
    Unified Data Processing Pipeline:
    Enriches ingested feed records with both Hinglish NLP slang classification
    and QR forensic threat intelligence.
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
    print("Executing Hinglish NLP analysis & QR forensic threat detection...")

    for item in data:
        item["processed"] = True

        # 1. Hinglish NLP Slang Analysis on text payload
        text_content = item.get("text_content") or item.get("text") or item.get("message_text") or item.get("message") or ""
        analysis = detector.analyze(text_content)
        item["nlp_analysis"] = {
            "normalized_text": analysis["normalized_text"],
            "detected_slangs": analysis["detected_slangs"],
            "risk_score": analysis["risk_score"],
            "is_suspicious": analysis["is_suspicious"],
        }

        # 2. QR Forensics on media attachments
        media_path = item.get("media_path")
        if media_path:
            candidate_paths = [
                Path(media_path),
                raw_dir / Path(media_path).name,
                images_dir / Path(media_path).name,
            ]
            resolved_img = next((p for p in candidate_paths if p.is_file()), None)

            if resolved_img:
                try:
                    qr_result = scan_qr_payload(str(resolved_img))
                    item["qr_scan"] = qr_result
                    if qr_result.get("qr_detected"):
                        if qr_result.get("status") in ("DRUG_DETECTED", "SUSPICIOUS"):
                            item["high_risk"] = True
                            item["risk_score"] = max(
                                item.get("risk_score", 0.0),
                                qr_result.get("confidence_score", 0.85)
                            )
                            item["threat_status"] = qr_result.get("status")
                        else:
                            item["threat_status"] = "CLEAN"
                except Exception as e:
                    print(f"Warning: QR scanning failed for {resolved_img}: {e}")

        # Combined risk threshold calculation
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
