"""Train a full-message drug-topic classifier from CardiffNLP X-Sensitive.

The source label means that a post is about drugs. It does not mean trafficking,
dealing, suspicious, or benign. This model must not be described as a dealer or
misuse classifier.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.linear_model import LogisticRegression

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "training" / "x_sensitive"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "registry" / "nlp_drug_topic.joblib"
DEFAULT_METRICS_PATH = PROJECT_ROOT / "models" / "registry" / "nlp_drug_topic.metrics.json"
SUPPORTED_SUFFIXES = {".csv", ".json", ".jsonl", ".parquet"}


def _read_records(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.casefold() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if path.suffix.casefold() == ".jsonl":
        with path.open("r", encoding="utf-8-sig") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    if path.suffix.casefold() == ".json":
        with path.open("r", encoding="utf-8-sig") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, list):
            return loaded
        if isinstance(loaded, dict):
            for key in ("data", "records", "examples"):
                if isinstance(loaded.get(key), list):
                    return loaded[key]
            if "text" in loaded:
                return [loaded]
        raise ValueError(f"Unsupported JSON dataset structure in {path}")
    if path.suffix.casefold() == ".parquet":
        import pandas as pd

        return pd.read_parquet(path).to_dict(orient="records")
    raise ValueError(f"Unsupported dataset file: {path}")


def _binary_drugs_label(row: Dict[str, Any]) -> int:
    value = row.get("drugs")
    if value is None and isinstance(row.get("labels"), (list, tuple, set)):
        value = int("drugs" in {str(label).casefold() for label in row["labels"]})
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)) and value in (0, 1):
        return int(value)
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "drug", "drugs", "drug_related"}:
        return 1
    if normalized in {"0", "false", "no", "not_drugs", "non_drug", "not_drug_related"}:
        return 0
    raise ValueError(f"Unrecognized X-Sensitive 'drugs' label: {value!r}")


def _split_name(path: Path, row: Dict[str, Any]) -> str | None:
    value = str(row.get("split", "")).strip().casefold()
    if value in {"train", "training"}:
        return "train"
    if value in {"validation", "valid", "val", "dev"}:
        return "validation"
    if value in {"test", "testing"}:
        return "test"
    for part in (path.stem.casefold(), *(item.casefold() for item in path.parts)):
        if re.search(r"(^|[-_])train(ing)?($|[-_])", part):
            return "train"
        if re.search(r"(^|[-_])(validation|valid|val|dev)($|[-_])", part):
            return "validation"
        if re.search(r"(^|[-_])test(ing)?($|[-_])", part):
            return "test"
    return None


def load_dataset(data_dir: Path) -> Tuple[Dict[str, List[str]], Dict[str, List[int]]]:
    """Read HF-exported files and retain their official splits when present."""
    if not data_dir.is_dir():
        raise FileNotFoundError(
            f"Dataset folder not found: {data_dir}. Download X-Sensitive files into this folder."
        )
    files = sorted(
        path for path in data_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() in SUPPORTED_SUFFIXES
    )
    if not files:
        raise FileNotFoundError(f"No supported CSV/JSON/JSONL/Parquet files found in {data_dir}")

    collected: Dict[str, List[Tuple[str, int]]] = {
        "train": [], "validation": [], "test": [], "unsplit": []
    }
    for path in files:
        records = _read_records(path)
        for row in records:
            text = row.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            label = _binary_drugs_label(row)
            split = _split_name(path, row) or "unsplit"
            collected[split].append((text.strip(), label))

    # Normalize exact-text duplicates. When official splits exist, the first
    # occurrence wins in train -> validation -> test order to avoid leakage.
    ordered_names = [name for name in ("train", "validation", "test") if collected[name]]
    if not ordered_names:
        records = _deduplicate(collected["unsplit"])
        if len({label for _, label in records}) < 2:
            raise ValueError("The dataset must contain both drugs=0 and drugs=1 examples")
        train, remainder = train_test_split(
            records, test_size=0.30, random_state=42,
            stratify=[label for _, label in records],
        )
        validation, test = train_test_split(
            remainder, test_size=0.50, random_state=42,
            stratify=[label for _, label in remainder],
        )
        collected = {"train": train, "validation": validation, "test": test}
        ordered_names = ["train", "validation", "test"]

    seen_texts = set()
    final: Dict[str, List[Tuple[str, int]]] = {}
    for split in ("train", "validation", "test"):
        if split not in ordered_names:
            continue
        unique = []
        for text, label in _deduplicate(collected[split]):
            key = re.sub(r"\s+", " ", text.casefold()).strip()
            if key in seen_texts:
                continue
            seen_texts.add(key)
            unique.append((text, label))
        final[split] = unique

    if "train" not in final:
        raise ValueError("Dataset must include a train split, or be an unsplit file")
    if len({label for _, label in final["train"]}) < 2:
        raise ValueError("The training split must contain both drugs=0 and drugs=1 examples")

    texts = {split: [text for text, _ in records] for split, records in final.items()}
    labels = {split: [label for _, label in records] for split, records in final.items()}
    return texts, labels


def _deduplicate(records: Iterable[Tuple[str, int]]) -> List[Tuple[str, int]]:
    unique: Dict[str, Tuple[str, int]] = {}
    for text, label in records:
        key = re.sub(r"\s+", " ", text.casefold()).strip()
        if key and key not in unique:
            unique[key] = (text, label)
    return list(unique.values())


def _build_model() -> Pipeline:
    features = FeatureUnion([
        ("word", TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), min_df=2,
            max_features=150_000, sublinear_tf=True,
        )),
        ("character", TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), min_df=2,
            max_features=150_000, sublinear_tf=True,
        )),
    ])
    return Pipeline([
        ("features", features),
        ("classifier", LogisticRegression(
            max_iter=2000, class_weight="balanced", random_state=42,
        )),
    ])


def _evaluate(model: Pipeline, texts: List[str], labels: List[int]) -> Dict[str, Any]:
    predicted = model.predict(texts)
    return {
        "rows": len(labels),
        "accuracy": float(accuracy_score(labels, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(labels, predicted)),
        "drug_related_precision": float(precision_score(labels, predicted, pos_label=1, zero_division=0)),
        "drug_related_recall": float(recall_score(labels, predicted, pos_label=1, zero_division=0)),
        "drug_related_f1": float(f1_score(labels, predicted, pos_label=1, zero_division=0)),
        "confusion_matrix_labels_0_1": confusion_matrix(labels, predicted, labels=[0, 1]).tolist(),
        "classification_report": classification_report(
            labels, predicted, labels=[0, 1],
            target_names=["not_drug_related", "drug_related"],
            output_dict=True, zero_division=0,
        ),
    }


def train(data_dir: Path, model_path: Path, metrics_path: Path) -> Dict[str, Any]:
    texts, labels = load_dataset(data_dir)
    model = _build_model()
    model.fit(texts["train"], labels["train"])

    metrics: Dict[str, Any] = {
        "task": "full_message_drug_topic_classification",
        "label_definition": "1=drug-related topic; 0=not labeled drug-related",
        "source_dataset": "cardiffnlp/x_sensitive",
        "class_counts": {
            split: {str(label): count for label, count in Counter(values).items()}
            for split, values in labels.items()
        },
        "splits": {},
        "limitations": [
            "The source labels drug-related topic, not suspicious dealing or trafficking.",
            "English social-media source; performance on Hinglish and simulation chat must be evaluated separately.",
            "A prediction is evidence for human review, not a finding about a person.",
        ],
    }
    for split in ("validation", "test"):
        if split in texts and texts[split]:
            metrics["splits"][split] = _evaluate(model, texts[split], labels[split])

    model_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--metrics-out", type=Path, default=DEFAULT_METRICS_PATH)
    args = parser.parse_args()
    print(json.dumps(train(args.data_dir, args.model_out, args.metrics_out), indent=2))


if __name__ == "__main__":
    main()
