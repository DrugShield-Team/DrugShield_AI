"""Train image-class and pill-shape evidence models from two Roboflow exports.

Usage:
  python ml/train_image_classifier.py --drug-zip PATH --pill-zip PATH

The drug export's Charas/Cocaine/Ganja/Heroine labels form the drug-related
classes; Flour and Salt are lookalike classes. The pill export is trained as
separate Capsule and Tablet presence signals and is never mapped to illicit.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
from PIL import Image
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.svm import SVC

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_pipeline.image_classifier import DRUG_CLASSES

DEFAULT_ARTIFACT = PROJECT_ROOT / "models" / "registry" / "image_analysis.joblib"
DEFAULT_METRICS = PROJECT_ROOT / "models" / "registry" / "image_analysis.metrics.json"
DRUG_LABELS = {"Charas", "Cocaine", "Flour", "Ganja", "Heroine", "Salt"}
PILL_LABELS = ("Capsule", "Tablet")
VALID_SPLITS = {"train", "valid", "validation", "test"}


def _safe_entry_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe path in dataset archive: {name}")
    return name


def _read_labels(zip_path: Path, split: str, expected_labels: set[str]) -> Tuple[List[str], List[Tuple[str, List[str]]]]:
    rows = []
    labels_seen: set[str] = set()
    with zipfile.ZipFile(zip_path) as archive:
        names = {_safe_entry_name(info.filename): info for info in archive.infolist()}
        for filename in sorted(names):
            if not filename.endswith("_classes.csv"):
                continue
            folder = filename.split("/", 1)[0].casefold()
            if folder not in VALID_SPLITS:
                continue
            normalized_split = "valid" if folder in {"valid", "validation"} else folder
            if normalized_split != split:
                continue
            reader = csv.DictReader(io.StringIO(archive.read(filename).decode("utf-8-sig")))
            headers = [str(h).strip() for h in (reader.fieldnames or [])]
            labels = [h for h in headers if h != "filename"]
            if not set(labels).issubset(expected_labels):
                raise ValueError(f"Unexpected labels in {filename}: {labels}")
            labels_seen.update(labels)
            for row in reader:
                normalized = {str(k).strip(): str(v).strip() for k, v in row.items() if k}
                image_name = _safe_entry_name(str(PurePosixPath(filename).parent / normalized["filename"]))
                if image_name not in names:
                    raise FileNotFoundError(f"Image listed in {filename} is missing: {image_name}")
                active = [label for label in labels if int(float(normalized.get(label, "0") or 0)) == 1]
                if not active:
                    raise ValueError(f"No active class labels in {filename}: {normalized}")
                rows.append((image_name, active))
        if not rows:
            raise ValueError(f"No labels found for split {split} in {zip_path}")
    return sorted(labels_seen), rows


def _features_for_split(zip_path: Path, split_rows: List[Tuple[str, List[str]]]) -> Tuple[np.ndarray, List[List[str]]]:
    features = []
    labels = []
    with zipfile.ZipFile(zip_path) as archive:
        for image_name, active_labels in split_rows:
            with Image.open(io.BytesIO(archive.read(image_name))) as image:
                features.append(image_path_features_from_image(image))
            labels.append(active_labels)
    return np.vstack(features), labels


def image_path_features_from_image(image: Any) -> np.ndarray:
    from src.ai_pipeline.image_classifier import extract_image_features
    return extract_image_features(image)


def _classify_drug_split(model: SVC, binary_model: SVC, features: np.ndarray, y_true: np.ndarray, classes: List[str]) -> Dict[str, Any]:
    predicted = model.predict(features)
    drug_indexes = [index for index, label in enumerate(classes) if label in DRUG_CLASSES]
    actual_drug = np.isin(y_true, drug_indexes).astype(int)
    binary_probabilities = binary_model.predict_proba(features)[:, list(binary_model.classes_).index(1)]
    predicted_drug = (binary_probabilities >= 0.5).astype(int)
    return {
        "rows": int(len(y_true)),
        "multiclass_accuracy": float(accuracy_score(y_true, predicted)),
        "multiclass_report": classification_report(
            y_true, predicted, labels=np.arange(len(classes)), target_names=classes,
            output_dict=True, zero_division=0,
        ),
        "drug_related_binary": {
            "precision": float(precision_score(actual_drug, predicted_drug, zero_division=0)),
            "recall": float(recall_score(actual_drug, predicted_drug, zero_division=0)),
            "f1": float(f1_score(actual_drug, predicted_drug, zero_division=0)),
            "balanced_accuracy": float(balanced_accuracy_score(actual_drug, predicted_drug)),
            "confusion_matrix_labels_0_1": _binary_confusion(actual_drug, predicted_drug),
        },
    }


def _binary_confusion(actual: np.ndarray, predicted: np.ndarray) -> List[List[int]]:
    return [
        [int(np.sum((actual == 0) & (predicted == 0))), int(np.sum((actual == 0) & (predicted == 1)))],
        [int(np.sum((actual == 1) & (predicted == 0))), int(np.sum((actual == 1) & (predicted == 1)))],
    ]


def train(drug_zip: Path, pill_zip: Path, artifact_path: Path, metrics_path: Path) -> Dict[str, Any]:
    drug_classes, drug_splits = {}, {}
    for split in ("train", "valid", "test"):
        drug_classes[split], drug_splits[split] = _read_labels(drug_zip, split, DRUG_LABELS)
    drug_classes_sorted = sorted(set().union(*[set(labels) for labels in drug_classes.values()]))
    if set(drug_classes_sorted) != DRUG_LABELS:
        raise ValueError(f"Drug dataset classes differ from expected six classes: {drug_classes_sorted}")

    pill_classes, pill_splits = {}, {}
    for split in ("train", "valid", "test"):
        pill_classes[split], pill_splits[split] = _read_labels(pill_zip, split, set(PILL_LABELS))
    pill_classes_sorted = sorted(set().union(*[set(labels) for labels in pill_classes.values()]))
    if set(pill_classes_sorted) != set(PILL_LABELS):
        raise ValueError(f"Pill dataset classes differ from expected labels: {pill_classes_sorted}")

    x_drug, y_drug = {}, {}
    for split, rows in drug_splits.items():
        x_drug[split], active = _features_for_split(drug_zip, rows)
        if any(len(item) != 1 for item in active):
            raise ValueError("Drug detection data must have exactly one class per image")
        drug_label_indexes = {label: index for index, label in enumerate(drug_classes_sorted)}
        y_drug[split] = np.asarray([drug_label_indexes[item[0]] for item in active], dtype=int)

    x_pill, y_pill = {}, {}
    for split, rows in pill_splits.items():
        x_pill[split], active = _features_for_split(pill_zip, rows)
        y_pill[split] = np.asarray(
            [[int(label in values) for label in pill_classes_sorted] for values in active],
            dtype=int,
        )

    drug_model = SVC(kernel="linear", class_weight="balanced", probability=True, random_state=42)
    drug_model.fit(x_drug["train"], y_drug["train"])
    y_drug_binary = {
        split: np.asarray([int(drug_classes_sorted[int(label)] in DRUG_CLASSES) for label in labels], dtype=int)
        for split, labels in y_drug.items()
    }
    drug_related_model = SVC(kernel="linear", class_weight="balanced", probability=True, random_state=42)
    drug_related_model.fit(x_drug["train"], y_drug_binary["train"])
    pill_models: Dict[str, SVC] = {}
    for index, label in enumerate(pill_classes_sorted):
        model = SVC(kernel="linear", class_weight="balanced", probability=True, random_state=42)
        model.fit(x_pill["train"], y_pill["train"][:, index])
        pill_models[label] = model

    metrics: Dict[str, Any] = {
        "task": "visual_evidence_classification",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_extractor": "96px grayscale HOG with RGB color histograms",
        "drug_model": {
            "dataset_archive": drug_zip.name,
            "classes": drug_classes_sorted,
            "drug_related_classes": sorted(DRUG_CLASSES),
            "lookalike_classes": sorted(DRUG_LABELS - DRUG_CLASSES),
            "counts": {
                split: dict(Counter(drug_classes_sorted[int(y)] for y in labels))
                for split, labels in y_drug.items()
            },
            "splits": {},
        },
        "pill_shape_models": {
            "dataset_archive": pill_zip.name,
            "classes": pill_classes_sorted,
            "counts": {
                split: {label: int(y_pill[split][:, i].sum()) for i, label in enumerate(pill_classes_sorted)}
                for split in y_pill
            },
            "multi_label_rows": {
                split: int(np.sum(y_pill[split].sum(axis=1) > 1)) for split in y_pill
            },
            "splits": {},
        },
        "limitations": [
            "The drug image export is very small and supports prototype evaluation only.",
            "Drug-related output is limited to the four labeled substance classes and two lookalikes.",
            "Capsule and Tablet are object-shape labels, not illicitness or suspiciousness labels.",
            "Pills dataset contains multi-label rows; predictions are auxiliary object evidence only.",
            "No OCR text-recognition training data is present in either archive.",
            "Image predictions require review and must not be treated as findings about a person.",
        ],
    }
    for split in ("valid", "test"):
        metrics["drug_model"]["splits"][split] = _classify_drug_split(
            drug_model, drug_related_model, x_drug[split], y_drug[split], drug_classes_sorted
        )
        pill_predictions = np.column_stack([
            (model.predict_proba(x_pill[split])[:, list(model.classes_).index(1)] >= 0.5).astype(int)
            for model in pill_models.values()
        ])
        metrics["pill_shape_models"]["splits"][split] = {
            "rows": int(len(y_pill[split])),
            "subset_accuracy": float(accuracy_score(y_pill[split], pill_predictions)),
            "macro_f1": float(f1_score(y_pill[split], pill_predictions, average="macro", zero_division=0)),
            "macro_precision": float(precision_score(y_pill[split], pill_predictions, average="macro", zero_division=0)),
            "macro_recall": float(recall_score(y_pill[split], pill_predictions, average="macro", zero_division=0)),
            "classification_report": classification_report(
                y_pill[split], pill_predictions, target_names=pill_classes_sorted,
                output_dict=True, zero_division=0,
            ),
        }

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "schema_version": 1,
        "drug_class_model": drug_model,
        "drug_related_model": drug_related_model,
        "drug_class_names": drug_classes_sorted,
        "pill_presence_models": pill_models,
        "pill_class_names": pill_classes_sorted,
        "metadata": {
            "task": metrics["task"],
            "drug_source": drug_zip.name,
            "pill_source": pill_zip.name,
            "decision_note": "Pills alone are not suspicious; model outputs are evidence candidates only.",
        },
    }, artifact_path)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drug-zip", type=Path, required=True)
    parser.add_argument("--pill-zip", type=Path, required=True)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--metrics-out", type=Path, default=DEFAULT_METRICS)
    args = parser.parse_args()
    print(json.dumps(train(args.drug_zip, args.pill_zip, args.model_out, args.metrics_out), indent=2))


if __name__ == "__main__":
    main()
