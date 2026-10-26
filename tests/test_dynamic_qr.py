"""Regression tests for QR payload decoding with the decoder-only contract."""

from PIL import Image
import qrcode

from src.ai_pipeline.qr_detector import scan_qr_payload


def test_decodes_multiple_qr_codes_without_assigning_risk(tmp_path):
    payloads = ["first test payload", "second test payload"]
    canvas = Image.new("RGB", (700, 350), "white")

    for index, payload in enumerate(payloads):
        qr_image = qrcode.make(payload).convert("RGB")
        qr_image = qr_image.resize((300, 300))
        canvas.paste(qr_image, (index * 350, 20))

    image_path = tmp_path / "multiple_qr.png"
    canvas.save(image_path)

    result = scan_qr_payload(image_path)

    assert result["qr_detected"] is True
    assert result["qr_decoded"] is True
    assert set(code["payload"] for code in result["all_decoded_codes"]) == set(payloads)
    assert "status" not in result
    assert "confidence_score" not in result
