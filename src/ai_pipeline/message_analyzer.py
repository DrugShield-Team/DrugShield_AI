"""Per-message orchestration for text, image, QR, and VPA evidence analysis.

Called by the local simulation API for each newly authored simulation event.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from src.ai_pipeline.nlp_classifier import (
    FullMessageDrugTopicClassifier,
    HinglishSlangDetector,
    get_drug_topic_classifier,
)
from src.ai_pipeline.image_classifier import (
    ImageAnalysisClassifier,
    get_image_classifier,
)
from src.ai_pipeline.qr_detector import scan_qr_payload
from src.ai_pipeline.vpa_extractor import extract_vpa_candidates


def analyze_message(
    text: str,
    image_paths: Optional[Iterable[str | Path]] = None,
    *,
    text_detector: Optional[HinglishSlangDetector] = None,
    message_classifier: Optional[FullMessageDrugTopicClassifier] = None,
    image_classifier: Optional[ImageAnalysisClassifier] = None,
    qr_scanner: Callable[[str], Dict[str, Any]] = scan_qr_payload,
) -> Dict[str, Any]:
    """Analyze one message and its images for text and visual evidence.

    Every supplied image is independently scanned for QR payloads and visual
    classes. QR decoding and VPA extraction are deterministic evidence
    extraction, while the visual model returns candidate class scores. None of
    these outputs independently establishes suspicious or illicit activity.
    """
    message_text = text if isinstance(text, str) else ""
    slang_dataset_status = "available"
    try:
        detector = text_detector or HinglishSlangDetector()
    except FileNotFoundError:
        # A source checkout may intentionally omit downloaded corpora. Keep
        # the trained model/QR path usable, but report that term matching is
        # unavailable instead of failing the entire message analysis.
        detector = HinglishSlangDetector(custom_lexicon={})
        slang_dataset_status = "missing_reviewed_dataset"
    text_result = detector.analyze(message_text)
    text_result["lexicon_status"] = slang_dataset_status
    classifier = message_classifier
    try:
        classifier = classifier or get_drug_topic_classifier()
        message_classification = classifier.analyze(message_text)
    except FileNotFoundError:
        message_classification = {
            "status": "model_not_trained",
            "task": "drug_topic_classification",
            "label": None,
            "probability": None,
            "class_probabilities": {},
        }

    qr_results = []
    image_results = []
    qr_payload_analyses = []
    vpa_results = extract_vpa_candidates(message_text, source="message_text")
    visual_model = image_classifier
    try:
        visual_model = visual_model or get_image_classifier()
        image_model_status = None
    except FileNotFoundError:
        image_model_status = "model_not_trained"

    for image_path in image_paths or []:
        path = Path(image_path)
        if not path.is_file():
            qr_results.append({"source_image": str(path), "error": "image_not_found"})
            image_results.append({"status": "image_not_found", "image_path": str(path)})
            continue

        if image_model_status:
            image_results.append({
                "status": image_model_status,
                "image_path": str(path),
                "task": "drug_class_and_pill_shape_evidence",
            })
        else:
            image_results.append(visual_model.analyze(path))

        try:
            qr_result = qr_scanner(str(path))
        except Exception as exc:
            qr_results.append(
                {"source_image": str(path), "error": f"qr_scan_failed: {exc}"}
            )
            continue
        qr_results.append(qr_result)
        payloads = []
        if isinstance(qr_result.get("payload_raw"), str):
            payloads.append(qr_result["payload_raw"])
        for decoded in qr_result.get("all_decoded_codes", []):
            if isinstance(decoded, dict) and isinstance(decoded.get("payload"), str):
                payloads.append(decoded["payload"])

        for payload in payloads:
            qr_payload_analyses.append({
                "source_image": str(path),
                "payload": payload,
                "text_analysis": detector.analyze(payload),
                "message_classification": (
                    classifier.analyze(payload)
                    if classifier is not None
                    else {
                        "status": "model_not_trained",
                        "task": "drug_topic_classification",
                        "label": None,
                        "probability": None,
                        "class_probabilities": {},
                    }
                ),
            })
            vpa_results.extend(
                extract_vpa_candidates(payload, source="decoded_qr_payload")
            )

    # Deduplicate across message text and QR payloads while preserving sources.
    unique_vpas = {}
    for item in vpa_results:
        key = item["candidate"].casefold()
        if key not in unique_vpas:
            unique_vpas[key] = {"candidate": item["candidate"], "sources": []}
        if item["source"] not in unique_vpas[key]["sources"]:
            unique_vpas[key]["sources"].append(item["source"])

    return {
        "text_analysis": text_result,
        "message_classification": message_classification,
        "image_classification": image_results,
        "qr_scans": qr_results,
        "qr_payload_text_analysis": qr_payload_analyses,
        "vpa_candidates": list(unique_vpas.values()),
    }
