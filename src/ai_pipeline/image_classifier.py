"""Visual image classification for known substance classes and pill shapes.

This module is deliberately separate from OCR and QR decoding. It reports
visual evidence candidates only; a pill/capsule prediction is not a finding
that an image is illicit or suspicious.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import numpy as np
from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "registry" / "image_analysis.joblib"
DRUG_CLASSES = {"Charas", "Cocaine", "Ganja", "Heroine"}
_IMAGE_SIZE = 96
_CELL_SIZE = 8
_ORIENTATION_BINS = 9


def extract_image_features(image: Image.Image) -> np.ndarray:
    """Create fixed-size HOG and color-histogram features for the trained models."""
    rgb = ImageOps.exif_transpose(image).convert("RGB").resize(
        (_IMAGE_SIZE, _IMAGE_SIZE), Image.Resampling.BILINEAR
    )
    pixels = np.asarray(rgb, dtype=np.float32) / 255.0
    gray = (
        0.299 * pixels[:, :, 0]
        + 0.587 * pixels[:, :, 1]
        + 0.114 * pixels[:, :, 2]
    )
    grad_y, grad_x = np.gradient(gray)
    magnitude = np.hypot(grad_x, grad_y)
    angle = np.mod(np.arctan2(grad_y, grad_x), np.pi)

    cells_per_axis = _IMAGE_SIZE // _CELL_SIZE
    cell_histograms = np.zeros(
        (cells_per_axis, cells_per_axis, _ORIENTATION_BINS), dtype=np.float32
    )
    bin_indices = np.minimum(
        (angle * (_ORIENTATION_BINS / np.pi)).astype(np.int32),
        _ORIENTATION_BINS - 1,
    )
    for cell_y in range(cells_per_axis):
        y0 = cell_y * _CELL_SIZE
        for cell_x in range(cells_per_axis):
            x0 = cell_x * _CELL_SIZE
            cell_histograms[cell_y, cell_x] = np.bincount(
                bin_indices[y0:y0 + _CELL_SIZE, x0:x0 + _CELL_SIZE].ravel(),
                weights=magnitude[y0:y0 + _CELL_SIZE, x0:x0 + _CELL_SIZE].ravel(),
                minlength=_ORIENTATION_BINS,
            )

    blocks = []
    for y in range(cells_per_axis - 1):
        for x in range(cells_per_axis - 1):
            block = cell_histograms[y:y + 2, x:x + 2].ravel()
            block = block / np.sqrt(float(np.dot(block, block)) + 1e-8)
            block = np.minimum(block, 0.2)
            block = block / np.sqrt(float(np.dot(block, block)) + 1e-8)
            blocks.append(block)

    color_features = []
    for channel in range(3):
        hist, _ = np.histogram(pixels[:, :, channel], bins=16, range=(0.0, 1.0))
        hist = hist.astype(np.float32)
        color_features.extend(hist / max(float(hist.sum()), 1.0))
    return np.concatenate((np.asarray(blocks, dtype=np.float32).ravel(), color_features))


def image_path_features(image_path: str | Path) -> np.ndarray:
    with Image.open(image_path) as image:
        return extract_image_features(image)


class ImageAnalysisClassifier:
    """Load the trained visual models and return class evidence for one image."""

    def __init__(self, model_path: Path = DEFAULT_MODEL_PATH):
        if not model_path.is_file():
            raise FileNotFoundError(
                f"Trained image model not found: {model_path}. "
                "Run ml/train_image_classifier.py with the reviewed image datasets."
            )
        artifact = joblib.load(model_path)
        if artifact.get("schema_version") != 1:
            raise ValueError("Unsupported image model artifact schema")
        self.drug_model = artifact["drug_class_model"]
        self.drug_related_model = artifact["drug_related_model"]
        self.drug_class_names = list(artifact["drug_class_names"])
        self.pill_models = artifact["pill_presence_models"]
        self.pill_class_names = list(artifact["pill_class_names"])
        self.metadata = artifact.get("metadata", {})

    def analyze(self, image_path: str | Path) -> Dict[str, Any]:
        path = Path(image_path)
        if not path.is_file():
            return {"status": "image_not_found", "image_path": str(path)}
        try:
            features = image_path_features(path).reshape(1, -1)
        except Exception as exc:
            return {
                "status": "image_read_failed",
                "image_path": str(path),
                "error": str(exc),
            }

        class_probabilities = self.drug_model.predict_proba(features)[0]
        drug_scores = {
            str(label): float(score)
            for label, score in zip(self.drug_class_names, class_probabilities)
        }
        binary_probabilities = self.drug_related_model.predict_proba(features)[0]
        positive_index = list(self.drug_related_model.classes_).index(1)
        drug_probability = float(binary_probabilities[positive_index])

        pill_scores: Dict[str, float] = {}
        for label, model in self.pill_models.items():
            probabilities = model.predict_proba(features)[0]
            positive_index = list(model.classes_).index(1)
            pill_scores[label] = float(probabilities[positive_index])

        return {
            "status": "predicted",
            "image_path": str(path),
            "task": "drug_class_and_pill_shape_evidence",
            "drug_class_probabilities": drug_scores,
            "drug_related_probability": float(drug_probability),
            "pill_shape_probabilities": pill_scores,
            "pill_shape_candidates": [
                label for label, score in pill_scores.items() if score >= 0.5
            ],
            "decision_note": (
                "Visual class scores are evidence candidates, not a determination "
                "of illicit activity. Pill/capsule predictions alone are not suspiciousness."
            ),
            "model_metadata": self.metadata,
        }


_GLOBAL_IMAGE_CLASSIFIER: Optional[ImageAnalysisClassifier] = None


def get_image_classifier() -> ImageAnalysisClassifier:
    """Load the image models once per process."""
    global _GLOBAL_IMAGE_CLASSIFIER
    if _GLOBAL_IMAGE_CLASSIFIER is None:
        _GLOBAL_IMAGE_CLASSIFIER = ImageAnalysisClassifier()
    return _GLOBAL_IMAGE_CLASSIFIER
