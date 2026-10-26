"""Configurable, review-only alert triggers for analysis evidence.

Scores from the current classifiers are not calibrated suspiciousness
probabilities. This policy emits review candidates and never makes a final
finding. Thresholds are provisional until calibrated on labeled simulation
messages.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List


def _number_from_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number between 0 and 1") from exc
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def review_thresholds() -> Dict[str, float]:
    """Return uncalibrated development thresholds; do not use as verdicts."""
    return {
        "drug_topic_model": _number_from_env("DRUG_TOPIC_REVIEW_THRESHOLD", 0.75),
        "image_drug_model": _number_from_env("IMAGE_DRUG_REVIEW_THRESHOLD", 0.95),
        "slang_risk_score": _number_from_env("SLANG_REVIEW_THRESHOLD", 0.35),
    }


def evaluate_for_human_review(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Create review-candidate reasons from distinct signals, not a blended score."""
    thresholds = review_thresholds()
    reasons: List[Dict[str, Any]] = []

    def inspect_text(text_result: Dict[str, Any], model_result: Dict[str, Any], source: str) -> None:
        slang_score = text_result.get("risk_score")
        if isinstance(slang_score, (int, float)) and slang_score >= thresholds["slang_risk_score"]:
            reasons.append({
                "signal": "reviewed_slang_threshold",
                "source": source,
                "value": float(slang_score),
                "threshold": thresholds["slang_risk_score"],
            })

        class_probabilities = model_result.get("class_probabilities") or {}
        drug_probability = class_probabilities.get("drug_related")
        if drug_probability is None and model_result.get("label") == "drug_related":
            drug_probability = model_result.get("probability")
        if isinstance(drug_probability, (int, float)) and drug_probability >= thresholds["drug_topic_model"]:
            reasons.append({
                "signal": "drug_topic_model_threshold",
                "source": source,
                "value": float(drug_probability),
                "threshold": thresholds["drug_topic_model"],
            })

    inspect_text(
        analysis.get("text_analysis", {}),
        analysis.get("message_classification", {}),
        "message_text",
    )
    for item in analysis.get("qr_payload_text_analysis", []):
        inspect_text(
            item.get("text_analysis", {}),
            item.get("message_classification", {}),
            "decoded_qr_payload",
        )

    for image_result in analysis.get("image_classification", []):
        score = image_result.get("drug_related_probability")
        if isinstance(score, (int, float)) and score >= thresholds["image_drug_model"]:
            reasons.append({
                "signal": "image_drug_model_threshold",
                "source": image_result.get("image_path", "image_attachment"),
                "value": float(score),
                "threshold": thresholds["image_drug_model"],
            })

    # A QR presence, a VPA-shaped string, or a pill/capsule shape alone is not
    # a trigger. They remain report evidence when another review signal fires.
    return {
        "review_required": bool(reasons),
        "triage_status": "pending_review" if reasons else "no_threshold_trigger",
        "reasons": reasons,
        "thresholds": thresholds,
        "policy_note": (
            "Thresholds are provisional development settings, not calibrated "
            "suspiciousness probabilities. Human review is required."
        ),
    }
