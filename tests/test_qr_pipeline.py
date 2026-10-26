from io import BytesIO
from pathlib import Path

from PIL import Image
import qrcode

from src.ai_pipeline.message_analyzer import analyze_message
from src.ai_pipeline.qr_detector import QRCodeDecoder, scan_qr_payload


class _NoRiskTextDetector:
    """Small test double so this suite isolates QR/VPA extraction."""

    def analyze(self, text):
        return {
            "normalized_text": text,
            "detected_slangs": [],
            "risk_score": 0.0,
            "is_suspicious": False,
        }


def _save_qr(path: Path, payload: str) -> Path:
    qrcode.make(payload).save(path)
    return path


def test_decodes_payload_as_evidence_without_risk_scoring(tmp_path):
    payload = "This is an ordinary test payload."
    image_path = _save_qr(tmp_path / "payload.png", payload)

    result = scan_qr_payload(image_path)

    assert result["qr_detected"] is True
    assert result["qr_decoded"] is True
    assert result["payload_raw"] == payload
    assert result["all_decoded_codes"][0]["payload"] == payload
    assert result["source_sha256"] is not None
    assert len(result["source_sha256"]) == 64
    assert "status" not in result
    assert "confidence_score" not in result
    assert "threat_indicators" not in result


def test_decodes_image_bytes_without_writing_a_file():
    payload = "in-memory QR payload"
    buffer = BytesIO()
    qrcode.make(payload).save(buffer, format="PNG")

    result = QRCodeDecoder().decode(buffer.getvalue())

    assert result["qr_decoded"] is True
    assert result["payload_raw"] == payload


def test_reports_image_without_qr(tmp_path):
    image_path = tmp_path / "blank.png"
    Image.new("RGB", (320, 240), color="white").save(image_path)

    result = scan_qr_payload(image_path)

    assert result["qr_detected"] is False
    assert result["qr_decoded"] is False
    assert result["payload_raw"] is None
    assert result["all_decoded_codes"] == []


def test_missing_image_returns_structured_error(tmp_path):
    result = scan_qr_payload(tmp_path / "missing.png")

    assert result["qr_detected"] is False
    assert result["qr_decoded"] is False
    assert result["error"] == "image_not_found"


def test_message_analysis_extracts_vpa_from_decoded_qr(tmp_path):
    payload = "upi://pay?pa=samplemerchant@okaxis&pn=Sample%20Shop&cu=INR"
    image_path = _save_qr(tmp_path / "upi.png", payload)

    result = analyze_message(
        "",
        [image_path],
        text_detector=_NoRiskTextDetector(),
    )

    assert result["qr_scans"][0]["qr_decoded"] is True
    assert result["qr_scans"][0]["payload_raw"] == payload
    assert result["vpa_candidates"] == [
        {
            "candidate": "samplemerchant@okaxis",
            "sources": ["decoded_qr_payload"],
        }
    ]
