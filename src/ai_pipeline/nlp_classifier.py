# src/ai_pipeline/nlp_classifier.py
"""
DrugShield AI - Narcotics NLP & Hinglish Slang Classifier
=========================================================
Analyzes textual payloads (such as decoded QR code contents, UPI notes,
chat snippets, and web URLs) to identify and flag narcotics, controlled
substances, street slang (including Hindi/Hinglish lexicons), and drug
trafficking solicitation intent.
"""

import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
from urllib.parse import unquote

# Path Resolution
FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent.parent
PROJECT_ROOT = SRC_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.constants import (
    NARCOTICS_TAXONOMY,
    ALL_DRUG_NAMES,
    SOLICITATION_KEYWORDS,
    HIGH_PRIORITY_DRUG_TOKENS,
    RISK_THRESHOLDS,
)


# Common false positive exclusions (e.g. "spot" has "pot", "device" has "ice", "folic acid")
BENIGN_PHRASES = {
    "folic acid", "salicylic acid", "hyaluronic acid", "amino acid", "citric acid", "ascorbic acid",
    "seaweed", "weed out", "green tea", "ice cream", "ice water", "dry ice",
    "flower pot", "cooking pot", "jackpot", "tea pot", "honey pot"
}

# Leetspeak substitution map for de-obfuscation
LEET_MAP = {
    '@': 'a', '4': 'a',
    '3': 'e',
    '1': 'i', '!': 'i', '|': 'i',
    '0': 'o',
    '5': 's', '$': 's',
    '7': 't',
    '8': 'b',
}

_SLANG_DATASET = PROJECT_ROOT / "data" / "training" / "drug_slang_terms_reviewed.csv"
DRUG_TOPIC_MODEL_PATH = PROJECT_ROOT / "models" / "registry" / "nlp_drug_topic.joblib"
_SUPPORTED_LANGUAGES = {"en", "hi"}
_HIGH_RISK_SLANG_CATEGORIES = {
    "cannabis", "stimulant", "opioid", "sedative", "dissociative",
    "hallucinogen", "depressant", "inhalant", "synthetic_cannabinoid",
    "pharmaceutical", "synthetic", "research_chemical",
}
_MEDIUM_RISK_SLANG_CATEGORIES = {"paraphernalia", "market", "method", "dose"}


def _normalize_slang_term(term: str) -> str:
    """Normalize a dataset term so matching respects token boundaries."""
    term = term.casefold().strip()
    term = re.sub(r"[^\w\s]", " ", term, flags=re.UNICODE)
    return re.sub(r"\s+", " ", term).strip()


def _load_reviewed_slang_lexicon(dataset_path: Path = _SLANG_DATASET) -> Dict[str, str]:
    """Load confirmed English/Hindi entries, excluding terms with conflicting labels."""
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Reviewed slang dataset not found: {dataset_path}")

    required = {"term", "language", "category", "review_status"}
    labels: Dict[str, Set[str]] = {}
    with dataset_path.open("r", encoding="utf-8-sig", newline="") as dataset_file:
        reader = csv.DictReader(dataset_file)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                "Reviewed slang dataset must contain columns: "
                + ", ".join(sorted(required))
            )

        for row in reader:
            if (row.get("review_status") or "").strip().casefold() != "confirmed":
                continue
            language = (row.get("language") or "").strip().casefold().split("-")[0]
            if language not in _SUPPORTED_LANGUAGES:
                continue
            term = _normalize_slang_term(row.get("term") or "")
            category = (row.get("category") or "").strip().casefold()
            if len(term) < 2 or not category:
                continue
            labels.setdefault(term, set()).add(category)

    # Do not silently select a category when the reviewed CSV conflicts.
    return {
        term: next(iter(categories))
        for term, categories in labels.items()
        if len(categories) == 1
    }


class HinglishSlangDetector:
    """
    Detects regional Hindi/Hinglish slang terms commonly used in localized
    narcotics trafficking networks across urban centers.
    """

    def __init__(self, custom_lexicon: Optional[Dict[str, str]] = None):
        raw_lexicon = (
            custom_lexicon
            if custom_lexicon is not None
            else _load_reviewed_slang_lexicon()
        )
        self.lexicon = {
            _normalize_slang_term(term): category.casefold()
            for term, category in raw_lexicon.items()
            if _normalize_slang_term(term)
        }
        self.high_risk_terms = _HIGH_RISK_SLANG_CATEGORIES
        self.medium_risk_terms = _MEDIUM_RISK_SLANG_CATEGORIES
        self._term_patterns = [
            (
                term,
                category,
                re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.UNICODE),
            )
            for term, category in sorted(
                self.lexicon.items(), key=lambda item: len(item[0]), reverse=True
            )
        ]

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""

        cleaned = _normalize_slang_term(text)
        cleaned = re.sub(r"(.)\1{2,}", r"\1\1", cleaned)
        for term, category, pattern in self._term_patterns:
            cleaned = pattern.sub(category, cleaned)
        return cleaned

    def analyze(self, text: str) -> Dict[str, Any]:
        original_text = text if isinstance(text, str) else ""
        normalized_text = self.normalize_text(original_text)
        searchable = _normalize_slang_term(original_text)
        searchable = re.sub(r"(.)\1{2,}", r"\1\1", searchable)
        detected_slangs = []
        matched_categories = []

        for term, category, pattern in self._term_patterns:
            if pattern.search(searchable):
                detected_slangs.append(term)
                matched_categories.append(category)

        score = 0.0
        for category in set(matched_categories):
            if category in self.high_risk_terms:
                score += 0.40
            elif category in self.medium_risk_terms:
                score += 0.25
            else:
                score += 0.10

        risk_score = round(min(1.0, score), 2)

        return {
            "original_text": text,
            "normalized_text": normalized_text,
            "detected_slangs": sorted(set(detected_slangs)),
            "slang_count": len(detected_slangs),
            "mapped_categories": sorted(set(matched_categories)),
            "risk_score": risk_score,
            "is_suspicious": risk_score >= 0.35,
        }


class FullMessageDrugTopicClassifier:
    """Classify a whole message as drug-related or not using a trained artifact.

    This predicts the source dataset's topic label only. It does not predict
    dealing, trafficking, suspiciousness, or whether a person committed an act.
    """

    def __init__(self, model_path: Path = DRUG_TOPIC_MODEL_PATH):
        if not model_path.is_file():
            raise FileNotFoundError(
                f"Trained NLP artifact not found: {model_path}. "
                "Download X-Sensitive to data/training/x_sensitive and run "
                "python ml/train_nlp_classifier.py first."
            )
        try:
            import joblib
        except ImportError as exc:
            raise RuntimeError(
                "scikit-learn/joblib are required to load the trained NLP model. "
                "Install requirements-training.txt."
            ) from exc
        self.model = joblib.load(model_path)

    def analyze(self, text: str) -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            return {
                "status": "empty_input",
                "task": "drug_topic_classification",
                "label": None,
                "probability": None,
                "class_probabilities": {},
            }

        probabilities = self.model.predict_proba([text])[0]
        classifier = self.model.named_steps["classifier"]
        class_probabilities = {
            ("drug_related" if int(label) == 1 else "not_drug_related"): float(probability)
            for label, probability in zip(classifier.classes_, probabilities)
        }
        prediction = int(self.model.predict([text])[0])
        label = "drug_related" if prediction == 1 else "not_drug_related"
        return {
            "status": "predicted",
            "task": "drug_topic_classification",
            "label": label,
            "probability": class_probabilities[label],
            "class_probabilities": class_probabilities,
        }


_GLOBAL_DRUG_TOPIC_CLASSIFIER: Optional[FullMessageDrugTopicClassifier] = None


def get_drug_topic_classifier() -> FullMessageDrugTopicClassifier:
    """Load the trained full-message classifier once per process."""
    global _GLOBAL_DRUG_TOPIC_CLASSIFIER
    if _GLOBAL_DRUG_TOPIC_CLASSIFIER is None:
        _GLOBAL_DRUG_TOPIC_CLASSIFIER = FullMessageDrugTopicClassifier()
    return _GLOBAL_DRUG_TOPIC_CLASSIFIER


class NLPNarcoticsClassifier:
    """
    Intelligent NLP and Lexical Engine to inspect text inside QR codes,
    detect narcotic substance names, classify illicit categories, and
    calculate solicitation threat scores.
    """

    def __init__(self):
        self.taxonomy = NARCOTICS_TAXONOMY
        self.solicitation_terms = [kw.lower() for kw in SOLICITATION_KEYWORDS]
        self._build_regex_patterns()

    def _build_regex_patterns(self):
        """Pre-compile regex patterns with strict word boundaries."""
        self.category_patterns: Dict[str, List[re.Pattern]] = {}
        for category, terms in self.taxonomy.items():
            patterns = []
            for term in terms:
                escaped = re.escape(term.lower())
                pat = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
                patterns.append((term, pat))
            self.category_patterns[category] = patterns

        self.solicitation_patterns = [
            (term, re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE))
            for term in self.solicitation_terms
        ]

    @staticmethod
    def deobfuscate(text: str) -> str:
        """
        De-cloaks leetspeak, spaced letters (e.g. 'm d m a' or 'l-s-d'),
        URL encoded strings, and punctuation separated tokens.
        """
        unquoted = unquote(text)
        lowered = unquoted.lower()
        decloaked = re.sub(r'(?<=\b[a-z0-9])[.\-_ ](?=[a-z0-9]\b)', '', lowered)
        leet_translated = "".join(LEET_MAP.get(ch, ch) for ch in decloaked)
        spaced = re.sub(r'[\_\-\.\/\+\&\=\?\:\@\%\,\;]', ' ', lowered)

        return f"{lowered} {decloaked} {leet_translated} {spaced}"

    def classify_text(self, text: Optional[str]) -> Dict[str, Any]:
        """
        Scans and inspects a text payload (QR content, UPI note, URL, or chat message).
        Returns detailed forensic intelligence including detected substances,
        categories, solicitation intent, confidence score, and alert risk level.
        """
        if not text or not str(text).strip():
            return {
                "is_drug_detected": False,
                "risk_level": "SAFE",
                "risk_score": 0.0,
                "confidence": 0.0,
                "detected_drug_names": [],
                "detected_categories": [],
                "solicitation_intent": False,
                "detected_solicitation_keywords": [],
                "explanation": "No text content provided for NLP analysis."
            }

        original_text = str(text).strip()
        search_corpus = self.deobfuscate(original_text)

        cleaned_corpus = search_corpus
        for benign in BENIGN_PHRASES:
            if benign in cleaned_corpus:
                cleaned_corpus = cleaned_corpus.replace(benign, " ")

        detected_drugs: Set[str] = set()
        detected_categories: Set[str] = set()
        high_priority_matches: Set[str] = set()

        for category, patterns in self.category_patterns.items():
            for term, pat in patterns:
                if pat.search(cleaned_corpus):
                    detected_drugs.add(term)
                    detected_categories.add(category)
                    if term in HIGH_PRIORITY_DRUG_TOKENS:
                        high_priority_matches.add(term)

        detected_solicitation: Set[str] = set()
        for term, pat in self.solicitation_patterns:
            if pat.search(cleaned_corpus):
                detected_solicitation.add(term)

        base_score = 0.0
        if detected_drugs:
            base_score += 0.40
            base_score += min(0.30, (len(detected_drugs) - 1) * 0.10)

        if high_priority_matches:
            base_score += 0.20

        if detected_solicitation:
            base_score += 0.25
            base_score += min(0.15, (len(detected_solicitation) - 1) * 0.05)

        risk_score = round(min(0.99, base_score), 2)
        is_drug_detected = len(detected_drugs) > 0 or (len(detected_solicitation) >= 2 and risk_score >= 0.40)

        if risk_score >= RISK_THRESHOLDS["CRITICAL"]:
            risk_level = "CRITICAL"
        elif risk_score >= RISK_THRESHOLDS["HIGH"]:
            risk_level = "HIGH"
        elif risk_score >= RISK_THRESHOLDS["MEDIUM"]:
            risk_level = "MEDIUM"
        elif risk_score >= RISK_THRESHOLDS["LOW"]:
            risk_level = "LOW"
        else:
            risk_level = "SAFE"

        if is_drug_detected:
            drugs_str = ", ".join(sorted(detected_drugs)) if detected_drugs else "None"
            cats_str = ", ".join(sorted(detected_categories)) if detected_categories else "Uncategorized"
            solicitation_str = f"with solicitation context ({', '.join(sorted(detected_solicitation))})" if detected_solicitation else "without explicit solicitation context"
            explanation = (
                f"[ALERT] Narcotic substance(s) detected: [{drugs_str}] "
                f"under class [{cats_str}] {solicitation_str}. Threat Score: {risk_score} ({risk_level})."
            )
        else:
            explanation = "No illicit narcotics or solicitation markers identified in QR payload."

        return {
            "is_drug_detected": is_drug_detected,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "confidence": risk_score,
            "detected_drug_names": sorted(list(detected_drugs)),
            "detected_categories": sorted(list(detected_categories)),
            "solicitation_intent": len(detected_solicitation) > 0,
            "detected_solicitation_keywords": sorted(list(detected_solicitation)),
            "high_priority_matches": sorted(list(high_priority_matches)),
            "analyzed_text_sample": original_text[:120] + ("..." if len(original_text) > 120 else ""),
            "explanation": explanation
        }


if __name__ == "__main__":
    classifier = NLPNarcoticsClassifier()
    hinglish = HinglishSlangDetector()

    test_samples = [
        "Fresh stock MDMA 1g 3k. Fast delivery in Bengaluru. DM @blr_supplies_bot UPI dealer@ybl",
        "Bhai maal chahiye setting kara de, gpay kar dunga",
        "upi://pay?pa=syndicate_score@ybl&pn=Delhi_Drop_Network&mc=5499&tn=LSD_Stamps_Deposit&am=4500",
        "https://www.wikipedia.org/wiki/Computer_science",
    ]

    print("=" * 70)
    print(" DRUGSHIELD AI - NLP & HINGLISH CLASSIFIER TEST RUN")
    print("=" * 70)

    for sample in test_samples:
        result = classifier.classify_text(sample)
        h_res = hinglish.analyze(sample)
        print(f"\nText: {sample}")
        print(f" -> NLP Flagged    : {result['is_drug_detected']} | Level: {result['risk_level']} | Score: {result['risk_score']}")
        print(f" -> Hinglish Slangs: {h_res['detected_slangs']} | Suspicious: {h_res['is_suspicious']}")
