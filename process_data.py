import json
import logging
from pathlib import Path
from src.ai_pipeline.qr_detector import scan_qr_payload

logger = logging.getLogger("DrugShield.ProcessData")


def process_raw_data():
    raw_file = Path("data/raw/ingested_raw_data.json")
    raw_dir = Path("data/raw")
    images_dir = raw_dir / "images"
    processed_dir = Path("data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)

    if not raw_file.exists():
        print(f"Error: {raw_file} not found. Run main.py first!")
        return

    print(f"Loading raw data from {raw_file}...")
    with open(raw_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Executing QR forensic intelligence and payload threat detection...")

    # Transform / normalize data with QR threat intelligence
    for item in data:
        item["processed"] = True

        # Check for media attachments to scan
        media_path = item.get("media_path")
        if media_path:
            # Resolve relative or filename paths
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

        # Fallback risk threshold evaluation
        if "high_risk" not in item:
            item["high_risk"] = item.get("risk_score", 0) > 0.50

    output_file = processed_dir / "processed_data.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"Data successfully processed and saved to: {output_file}")


if __name__ == "__main__":
    process_raw_data()