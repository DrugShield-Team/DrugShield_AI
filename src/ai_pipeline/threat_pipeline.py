"""
DrugShield AI - Central Threat Evaluation & Alert Dispatch Engine
=================================================================
Connects passive crawlers directly to:
- Module 2: NLP Classifier (nlp_classifier.py) & OCR Parser (ocr_parser.py) & QR Detector (qr_detector.py)
- Module 3: Financial & UPI Parser (upi_parser.py)
- Module 4: Neo4j Graph DB (neo4j_client.py) & PostgreSQL DB (postgres_client.py)
- Notification: Native OS Desktop Popup Toast (popup_alert.py)
- Model Training Dataset Builder: Appends to `data/raw/training_dataset.jsonl`
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent.parent
PROJECT_ROOT = SRC_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RAW_DIR = PROJECT_ROOT / "data" / "raw"
IMAGES_DIR = RAW_DIR / "images"
TRAINING_DATASET_FILE = RAW_DIR / "training_dataset.jsonl"
MASTER_RAW_DATA_FILE = RAW_DIR / "ingested_raw_data.json"

# Import Pipeline Modules
from src.ai_pipeline.nlp_classifier import NLPNarcoticsClassifier, HinglishSlangDetector
from src.ai_pipeline.ocr_parser import extract_text_from_image
from src.ai_pipeline.qr_detector import scan_qr_payload
from src.osint_triangulation.upi_parser import extract_financial_entities
from src.ai_pipeline.exif_extractor import extract_exif_metadata
from src.database.neo4j_client import push_threat_to_neo4j
from src.database.postgres_client import push_threat_to_postgres
try:
    from src.notifications.popup_alert import trigger_threat_popup
except ImportError:
    def trigger_threat_popup(record: Dict[str, Any]):
        pass

# Initialize Global Classifiers
nlp_classifier = NLPNarcoticsClassifier()
try:
    hinglish_detector = HinglishSlangDetector()
except FileNotFoundError:
    hinglish_detector = HinglishSlangDetector(custom_lexicon={})


def append_to_training_dataset(record: Dict[str, Any]):
    """
    Appends an interaction into the centralized training dataset file at
    data/raw/training_dataset.jsonl with exact target formatting.
    """
    try:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        dataset_entry = {
            "id": record.get("id") or f"live_msg_{int(datetime.utcnow().timestamp() * 1000)}",
            "platform": record.get("platform", "live_stream"),
            "timestamp": record.get("timestamp") or datetime.utcnow().isoformat(),
            "message_text": record.get("message_text") or record.get("message_body") or record.get("text_content") or "",
            "flagged_status": bool(record.get("flagged_status", False)),
            "threat_score": float(record.get("threat_score", 0.05)),
            "extracted_entities": {
                "upi_ids": record.get("extracted_entities", {}).get("upi_ids", []),
                "bank_accounts": record.get("extracted_entities", {}).get("bank_accounts", [])
            },
            "media_path": record.get("media_path")
        }

        with open(TRAINING_DATASET_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(dataset_entry) + "\n")
    except Exception as e:
        print(f"[-] Warning: Failed appending to training_dataset.jsonl: {e}")


def sync_master_raw_data(record: Dict[str, Any]):
    """Maintains master ingested_raw_data.json without duplication."""
    try:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        existing = []
        if MASTER_RAW_DATA_FILE.exists():
            try:
                with open(MASTER_RAW_DATA_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    if not isinstance(existing, list):
                        existing = []
            except Exception:
                existing = []

        existing.append(record)
        with open(MASTER_RAW_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[-] Warning syncing to master raw data: {e}")


def evaluate_live_message_threat(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Comprehensive Threat Intelligence Evaluation:
    Streams live text and binary attachment through Module 2 & Module 3,
    calculates dynamic threat score, triggers alerts, and archives for model training.
    """
    msg_text = record.get("message_text") or record.get("message_body") or record.get("text_content") or ""
    media_path = record.get("media_path")
    sender_id = record.get("sender_id") or record.get("sender_username") or "unknown"
    platform = record.get("platform", "live_stream")
    timestamp = record.get("timestamp") or datetime.utcnow().isoformat()
    record_id = record.get("id") or f"live_msg_{int(datetime.utcnow().timestamp() * 1000)}"

    # 1. Module 2: NLP Classification
    nlp_res = nlp_classifier.classify_text(msg_text)
    hinglish_res = hinglish_detector.analyze(msg_text)

    # 2. Module 3: Financial & UPI Entity Extraction on primary text
    fin_res = extract_financial_entities(msg_text)

    # 3. Media Forensics (OCR, QR & EXIF)
    ocr_res = {"success": False, "raw_text": "", "detected_drugs": []}
    qr_res = {"qr_detected": False, "confidence_score": 0.0}
    exif_res = {"has_exif": False, "has_gps": False}

    resolved_media_path = None
    if media_path:
        candidates = [
            Path(media_path),
            PROJECT_ROOT / media_path,
            RAW_DIR / Path(media_path).name,
            IMAGES_DIR / Path(media_path).name
        ]
        resolved_media_path = next((p for p in candidates if p.is_file()), None)

        if resolved_media_path:
            # Run OCR
            try:
                ocr_res = extract_text_from_image(str(resolved_media_path))
                if ocr_res.get("raw_text"):
                    ocr_fin = extract_financial_entities(ocr_res["raw_text"])
                    # Merge financial entities from OCR
                    fin_res["upi_ids"] = list(set(fin_res["upi_ids"] + ocr_fin["upi_ids"]))
                    fin_res["bank_accounts"] = list(set(fin_res["bank_accounts"] + ocr_fin["bank_accounts"]))
                    fin_res["phone_numbers"] = list(set(fin_res["phone_numbers"] + ocr_fin["phone_numbers"]))
            except Exception as e:
                print(f"[-] OCR inspection warning on {resolved_media_path.name}: {e}")

            # Run QR forensics
            try:
                qr_res = scan_qr_payload(str(resolved_media_path))
                if qr_res.get("qr_detected") and qr_res.get("decoded_payload"):
                    qr_fin = extract_financial_entities(qr_res["decoded_payload"])
                    fin_res["upi_ids"] = list(set(fin_res["upi_ids"] + qr_fin["upi_ids"]))
                    fin_res["bank_accounts"] = list(set(fin_res["bank_accounts"] + qr_fin["bank_accounts"]))
            except Exception as e:
                print(f"[-] QR inspection warning on {resolved_media_path.name}: {e}")

            # Run EXIF metadata extraction
            try:
                exif_res = extract_exif_metadata(resolved_media_path)
                if exif_res.get("has_gps"):
                    gps_coord = f"{exif_res['latitude']:.6f}, {exif_res['longitude']:.6f}"
                    if gps_coord not in fin_res["gps_coordinates"]:
                        fin_res["gps_coordinates"].append(gps_coord)
            except Exception as e:
                print(f"[-] EXIF inspection warning on {resolved_media_path.name}: {e}")

    # 4. Consolidate Detected Substances & Entities
    detected_drugs = list(set(
        nlp_res.get("detected_drug_names", []) +
        hinglish_res.get("detected_slangs", []) +
        ocr_res.get("detected_drugs", [])
    ))

    # 5. Dynamic Threat Score Calculation
    base_nlp_score = nlp_res.get("risk_score", 0.0)
    hinglish_score = hinglish_res.get("risk_score", 0.0)
    fin_score = fin_res.get("financial_threat_score", 0.0)
    qr_confidence = qr_res.get("confidence_score", 0.0) if qr_res.get("qr_detected") else 0.0

    # Boost score if narcotics intent + financial details are co-present (Dealing signature)
    dealing_multiplier = 1.0
    if detected_drugs and (fin_res.get("upi_ids") or fin_res.get("bank_accounts")):
        dealing_multiplier = 1.30
    elif nlp_res.get("solicitation_intent") and fin_res.get("has_financial_intent"):
        dealing_multiplier = 1.25

    combined_score = max(base_nlp_score, hinglish_score, qr_confidence)
    if fin_score > 0:
        combined_score = max(combined_score, 0.40 * fin_score + 0.60 * combined_score)

    final_threat_score = round(min(0.99, combined_score * dealing_multiplier), 2)
    is_flagged = final_threat_score >= 0.60 or len(detected_drugs) > 0

    # 6. Build Enriched Threat Record
    enriched_record = {
        "id": record_id,
        "platform": platform,
        "timestamp": timestamp,
        "sender_id": sender_id,
        "sender_username": record.get("sender_username"),
        "chat_id": record.get("chat_id"),
        "message_text": msg_text,
        "message_body": msg_text,
        "threat_score": final_threat_score,
        "flagged_status": is_flagged,
        "isFlagged": is_flagged,
        "has_media": bool(media_path),
        "media_path": str(resolved_media_path) if resolved_media_path else media_path,
        "extracted_entities": {
            "narcotics_detected": detected_drugs,
            "upi_ids": fin_res.get("upi_ids", []),
            "bank_accounts": fin_res.get("bank_accounts", []),
            "ifsc_codes": fin_res.get("ifsc_codes", []),
            "phone_numbers": fin_res.get("phone_numbers", []),
            "gps_coordinates": fin_res.get("gps_coordinates", []),
            "crypto_wallets": fin_res.get("crypto_wallets", {})
        },
        "nlp_analysis": {
            "risk_score": base_nlp_score,
            "risk_level": nlp_res.get("risk_level", "SAFE"),
            "solicitation_intent": nlp_res.get("solicitation_intent", False)
        },
        "ocr_forensics": {
            "performed": bool(resolved_media_path),
            "text_extracted": bool(ocr_res.get("raw_text"))
        },
        "exif_forensics": exif_res,
        "qr_scan": qr_res
    }

    # 7. Action On Flagged Threat (Score >= 0.60)
    if is_flagged:
        print(f"\n[Threat Pipeline] 🚨 THREAT FLAGGED (Score: {final_threat_score:.2f} >= 0.60)")
        print(f"    Platform   : {platform}")
        print(f"    Author     : {sender_id}")
        print(f"    Substances : {', '.join(detected_drugs) or 'Illicit Solicitation'}")
        if fin_res.get("upi_ids"):
            print(f"    UPI IDs    : {', '.join(fin_res['upi_ids'])}")

        # Push to Module 4: Neo4j Graph DB
        push_threat_to_neo4j(enriched_record)

        # Push to Module 4: PostgreSQL Database
        push_threat_to_postgres(enriched_record)

        # Fire Native OS Desktop Toast Alert
        trigger_threat_popup(enriched_record)

    # 8. Model Training Dataset Builder: Append to data/raw/training_dataset.jsonl
    append_to_training_dataset(enriched_record)

    # 9. Sync Master Landing Zone
    sync_master_raw_data(enriched_record)

    return enriched_record
