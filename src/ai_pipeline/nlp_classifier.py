# src/ai_pipeline/nlp_classifier.py
"""
DrugShield AI - Narcotics NLP & Illicit Solicitation Classifier
================================================================
Analyzes textual payloads (such as decoded QR code contents, UPI notes,
chat snippets, and web URLs) to identify and flag narcotics, controlled
substances, street slang, and drug trafficking solicitation intent.
"""

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

try:
    from config.constants import (
        NARCOTICS_TAXONOMY,
        ALL_DRUG_NAMES,
        SOLICITATION_KEYWORDS,
        HIGH_PRIORITY_DRUG_TOKENS,
        RISK_THRESHOLDS,
    )
except ImportError:
    # Standalone Fallback
    NARCOTICS_TAXONOMY = {
        "cannabis": ["weed", "ganja", "charas", "hashish", "cannabis", "og kush", "bhang"],
        "opioids": ["heroin", "chitta", "smack", "fentanyl", "tramadol", "opium", "morphine"],
        "stimulants": ["cocaine", "coke", "mdma", "molly", "ecstasy", "meth", "mephedrone", "m-cat", "ice"],
        "psychedelics": ["lsd", "acid", "blotter", "stamp", "shrooms", "psilocybin", "ketamine"],
        "pharmaceutical_sedatives": ["alprazolam", "xanax", "valium", "diazepam", "lean"],
    }
    ALL_DRUG_NAMES = {term for terms in NARCOTICS_TAXONOMY.values() for term in terms}
    SOLICITATION_KEYWORDS = [
        "score", "stash", "plug", "dealer", "drop", "dead drop", "pin", "token",
        "delivery", "stock", "pure", "1g", "5g", "menu", "rates"
    ]
    HIGH_PRIORITY_DRUG_TOKENS = {"mdma", "lsd", "chitta", "heroin", "cocaine", "coke", "meth", "weed", "ganja"}
    RISK_THRESHOLDS = {"CRITICAL": 0.75, "HIGH": 0.50, "MEDIUM": 0.30, "LOW": 0.15}


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
                # Use word boundary to avoid substring collisions
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
        and URL encoded strings.
        """
        # 1. URL decode
        unquoted = unquote(text)

        # 2. Lowercase
        lowered = unquoted.lower()

        # 3. Replace common symbols that split characters: e.g. "m.d.m.a" or "l-s-d" -> "mdma", "lsd"
        # Match single characters separated by dots/dashes/spaces
        decloaked = re.sub(r'(?<=\b[a-z0-9])[.\-_ ](?=[a-z0-9]\b)', '', lowered)

        # 4. Leetspeak translation
        leet_translated = "".join(LEET_MAP.get(ch, ch) for ch in decloaked)

        # 5. Punctuation to space conversion for separated tokens (e.g. 'LSD_Stamps' -> 'lsd stamps')
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

        # Filter out common benign medical/food phrases (e.g., "citric acid", "ice cream")
        cleaned_corpus = search_corpus
        for benign in BENIGN_PHRASES:
            if benign in cleaned_corpus:
                cleaned_corpus = cleaned_corpus.replace(benign, " ")

        detected_drugs: Set[str] = set()
        detected_categories: Set[str] = set()
        high_priority_matches: Set[str] = set()

        # 1. Scan for drug substances across all taxonomic categories
        for category, patterns in self.category_patterns.items():
            for term, pat in patterns:
                if pat.search(cleaned_corpus):
                    detected_drugs.add(term)
                    detected_categories.add(category)
                    if term in HIGH_PRIORITY_DRUG_TOKENS:
                        high_priority_matches.add(term)

        # 2. Scan for solicitation and trafficking intent keywords
        detected_solicitation: Set[str] = set()
        for term, pat in self.solicitation_patterns:
            if pat.search(cleaned_corpus):
                detected_solicitation.add(term)

        # 3. Score calculation
        base_score = 0.0

        if detected_drugs:
            base_score += 0.40  # Primary drug substance identified
            base_score += min(0.30, (len(detected_drugs) - 1) * 0.10)  # Multi-substance menu boost

        if high_priority_matches:
            base_score += 0.20  # Hard/scheduled narcotics detected (MDMA, Heroin, Cocaine, Meth, LSD)

        if detected_solicitation:
            base_score += 0.25  # Commercial dealing / delivery / drop context present
            base_score += min(0.15, (len(detected_solicitation) - 1) * 0.05)

        # Cap confidence at 0.99
        risk_score = round(min(0.99, base_score), 2)
        is_drug_detected = len(detected_drugs) > 0 or (len(detected_solicitation) >= 2 and risk_score >= 0.40)

        # Determine risk level
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

        # Construct actionable forensic explanation
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


# Quick diagnostic helper
if __name__ == "__main__":
    classifier = NLPNarcoticsClassifier()

    test_samples = [
        "Fresh stock MDMA 1g 3k. Fast delivery in Bengaluru. DM @blr_supplies_bot UPI dealer@ybl",
        "upi://pay?pa=syndicate_score@ybl&pn=Delhi_Drop_Network&mc=5499&tn=LSD_Stamps_Deposit&am=4500",
        "We have top quality weed, ganja, and chitta ready for pin drop.",
        "https://chat.whatsapp.com/inv?tag=rave_supplies_mdma_pills",
        "https://www.wikipedia.org/wiki/Computer_science",
        "Organic green tea with citric acid and fresh apples"
    ]

    print("=" * 70)
    print(" DRUGSHIELD AI - NLP NARCOTICS CLASSIFIER TEST RUN")
    print("=" * 70)

    for sample in test_samples:
        result = classifier.classify_text(sample)
        print(f"\nText: {sample}")
        print(f" -> Flagged: {result['is_drug_detected']} | Level: {result['risk_level']} | Score: {result['risk_score']}")
        print(f" -> Drugs  : {result['detected_drug_names']}")
        print(f" -> Classes: {result['detected_categories']}")
        print(f" -> Summary: {result['explanation']}")
