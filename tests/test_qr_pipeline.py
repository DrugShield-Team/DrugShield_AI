import os
import sys
import json
import tempfile
from pathlib import Path
from PIL import Image
import qrcode

# Path hook
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_pipeline.qr_detector import (
    QRThreatDetector,
    scan_qr_payload,
    get_qr_detector,
    STATUS_DRUG_DETECTED,
    STATUS_SUSPICIOUS,
    STATUS_CLEAN,
)
from process_data import process_raw_data


def test_qr_clean_payload():
    """Verify benign text or legitimate web URLs evaluate as CLEAN."""
    detector = get_qr_detector()
    res = detector.evaluate_threat("https://en.wikipedia.org/wiki/Computer_science")
    assert res["status"] == STATUS_CLEAN
    assert res["confidence_score"] == 0.0
    assert len(res["threat_indicators"]) == 0
    assert len(res["extracted_keywords"]) == 0


def test_qr_drug_detected_explicit_substances():
    """Verify explicit illicit substance names trigger DRUG_DETECTED."""
    detector = get_qr_detector()
    samples = [
        ("MDMA 1g 3k menu delivery", "mdma"),
        ("Pure Methamphetamine and Cocaine available", "cocaine"),
        ("Weed, Ganja and Charas in stock", "weed"),
        ("Order Tramadol and Xanax pills today", "tramadol"),
    ]
    for text, expected_keyword in samples:
        res = detector.evaluate_threat(text)
        assert res["status"] == STATUS_DRUG_DETECTED, f"Failed for {text}"
        assert res["confidence_score"] >= 0.85
        assert any(expected_keyword in kw.lower() for kw in res["extracted_keywords"])
        assert len(res["threat_indicators"]) > 0


def test_qr_drug_detected_contraband_menu():
    """Verify contraband menu and dealing phrases trigger DRUG_DETECTED."""
    detector = get_qr_detector()
    res = detector.evaluate_threat("Fresh stock price list: 1g 500, stealth delivery vacuum sealed")
    assert res["status"] == STATUS_DRUG_DETECTED
    assert res["confidence_score"] >= 0.85
    assert any("CONTRABAND_MENU" in ind for ind in res["threat_indicators"])


def test_qr_suspicious_encrypted_redirects():
    """Verify Telegram bots, Wickr, Signal, and Darknet mirrors trigger SUSPICIOUS."""
    detector = get_qr_detector()

    # Telegram Bot
    res_tg = detector.evaluate_threat("https://t.me/delhi_connect_bot for inquiries")
    assert res_tg["status"] == STATUS_SUSPICIOUS
    assert any("Telegram Bot" in ind for ind in res_tg["threat_indicators"])

    # Wickr
    res_wickr = detector.evaluate_threat("Reach out on Wickr: private_vendor_01")
    assert res_wickr["status"] == STATUS_SUSPICIOUS
    assert any("Wickr" in ind for ind in res_wickr["threat_indicators"])

    # Signal
    res_signal = detector.evaluate_threat("Encrypted chats on Signal: +919876543210")
    assert res_signal["status"] == STATUS_SUSPICIOUS
    assert any("Signal" in ind for ind in res_signal["threat_indicators"])

    # Darknet .onion
    res_onion = detector.evaluate_threat("http://marketdarknet456abc.onion/shop")
    assert res_onion["status"] == STATUS_SUSPICIOUS
    assert any("DARKNET_MIRROR" in ind for ind in res_onion["threat_indicators"])


def test_qr_suspicious_dead_drop_coordinates():
    """Verify dead-drop coordinates trigger SUSPICIOUS."""
    detector = get_qr_detector()
    res = detector.evaluate_threat("Dead-drop package located at: 28.6139, 77.2090")
    assert res["status"] == STATUS_SUSPICIOUS
    assert any("DEAD_DROP" in ind for ind in res["threat_indicators"])


def test_qr_suspicious_pill_keywords():
    """Verify generic pill/capsule keywords trigger SUSPICIOUS."""
    detector = get_qr_detector()
    res = detector.evaluate_threat("New shipment of pressies, bars and capsules")
    assert res["status"] == STATUS_SUSPICIOUS
    assert any("PILL_INDICATOR" in ind for ind in res["threat_indicators"])


def test_scan_synthetic_drug_qr_image():
    """Generate synthetic QR image with drug payload, scan it, and verify crops and intel."""
    fixtures_dir = Path("data/forensic_cache/test_fixtures")
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    test_img_path = fixtures_dir / "test_synthetic_drug_qr.png"

    # Create synthetic QR image with drug payload
    payload = "MDMA 2g 5k rate list DM @delhi_rave_bot UPI dealer@ybl"
    qr_img = qrcode.make(payload)
    qr_img.save(str(test_img_path))

    res = scan_qr_payload(str(test_img_path))

    assert res["qr_detected"] is True
    assert res["payload_raw"] == payload
    assert res["status"] == STATUS_DRUG_DETECTED
    assert res["confidence_score"] >= 0.88
    assert "mdma" in [kw.lower() for kw in res["extracted_keywords"]]

    # Verify crop cached
    assert res.get("crop_path") is not None
    assert Path(res["crop_path"]).is_file()

    # Verify intelligence recorded in data/qr_deep_intel.json
    intel_file = Path("data/qr_deep_intel.json")
    assert intel_file.is_file()
    with open(intel_file, "r", encoding="utf-8") as f:
        records = json.load(f)
        matching = [r for r in records if r.get("payload_raw") == payload]
        assert len(matching) > 0


def test_scan_image_without_qr():
    """Verify scanning an image with no QR returns qr_detected=False and status=CLEAN."""
    # Use existing sample image
    sample_img = Path("data/raw/sample_image.jpg")
    if sample_img.is_file():
        res = scan_qr_payload(str(sample_img))
        assert res["qr_detected"] is False
        assert res["status"] == STATUS_CLEAN
        assert res["confidence_score"] == 0.0
        assert res["payload_raw"] is None


def test_process_data_integration():
    """Verify process_data.py runs end-to-end and includes QR forensics."""
    process_raw_data()
    output_file = Path("data/processed/processed_data.json")
    assert output_file.is_file()
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) > 0
    assert all("processed" in item for item in data)


if __name__ == "__main__":
    print("\n=======================================================")
    print("   RUNNING DRUGSHIELD AI QR PIPELINE TEST SUITE       ")
    print("=======================================================")
    tests = [
        test_qr_clean_payload,
        test_qr_drug_detected_explicit_substances,
        test_qr_drug_detected_contraband_menu,
        test_qr_suspicious_encrypted_redirects,
        test_qr_suspicious_dead_drop_coordinates,
        test_qr_suspicious_pill_keywords,
        test_scan_synthetic_drug_qr_image,
        test_scan_image_without_qr,
        test_process_data_integration,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f" [PASS] {t.__name__}")
            passed += 1
        except Exception as e:
            print(f" [FAIL] {t.__name__}: {e}")
            raise e

    print(f"\nAll {passed}/{len(tests)} tests PASSED successfully!\n")

