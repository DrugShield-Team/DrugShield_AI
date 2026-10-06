import re
from typing import Dict, List, Any

# Hinglish Slang Lexicon Mapping
HINGLISH_DRUG_LEXICON = {
    # --- CANNABIS / WEED / HASH ---
    "maal": "cannabis",
    "maall": "cannabis",
    "maaaal": "cannabis",
    "samaan": "contraband",
    "samān": "contraband",
    "stuff": "cannabis",
    "ganja": "cannabis",
    "gaanja": "cannabis",
    "bhang": "cannabis",
    "charas": "hashish",
    "hash": "hashish",
    "potti": "cannabis",
    "fukna": "smoke_weed",
    "joint": "cannabis_joint",
    "greens": "cannabis",
    "grass": "cannabis",
    "score": "buy_drugs",
    "skore": "buy_drugs",

    # --- SYNTHETICS / POWDERS / OPIATES ---
    "chitta": "heroin",
    "chittaah": "heroin",
    "powder": "cocaine",
    "meth": "methamphetamine",
    "ice": "methamphetamine",
    "meow meow": "mephedrone",
    "mcat": "mephedrone",
    "md": "mdma",
    "molly": "mdma",
    "ecstasy": "mdma",
    "acid": "lsd",
    "blotter": "lsd",
    "stamp": "lsd",
    "pudgi": "drug_packet",
    "puddi": "drug_packet",
    "pudiya": "drug_packet",
    "pudya": "drug_packet",
    "packet": "drug_packet",
    "tokri": "bulk_package",

    # --- PRESCRIPTION DRUGS & COUGH SYRUPS ---
    "codene": "codeine",
    "cough syrup": "codeine_syrup",
    "nasha": "intoxication",
    "goli": "narcotic_pill",
    "pills": "narcotic_pill",
    "tramadol": "opioid_pill",

    # --- TRANSACTIONAL & LOGISTICAL SLANG ---
    "setting": "deal_arrangement",
    "scene": "meetup_location",
    "scenic": "meetup_location",
    "spot": "drop_off_point",
    "bhai": "dealer_contact",
    "peddler": "drug_dealer",
    "bhagwan": "primary_supplier",
    "kab": "when",
    "kab milega": "delivery_time_inquiry",
    "chahiye": "requirement_inquiry",
    "kitna": "quantity_inquiry",
    "rate": "price_inquiry",
    "bhao": "price_inquiry",
    "dam": "price_inquiry",

    # --- FINANCIAL & DIGITAL PAYMENT INDICATORS ---
    "gpay": "digital_payment",
    "phonepe": "digital_payment",
    "paytm": "digital_payment",
    "upi": "digital_payment",
    "qr": "qr_code_payment",
    "advance": "upfront_payment",
    "cash": "cash_payment",
    "cod": "cash_on_delivery",
}


class HinglishSlangDetector:
    def __init__(self, custom_lexicon: Dict[str, str] = None):
        self.lexicon = custom_lexicon or HINGLISH_DRUG_LEXICON
        
        self.high_risk_terms = {
            "heroin", "cocaine", "methamphetamine", "mephedrone", 
            "lsd", "mdma", "drug_packet", "buy_drugs"
        }
        self.medium_risk_terms = {
            "cannabis", "hashish", "smoke_weed", "codeine", "narcotic_pill"
        }

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""

        cleaned = text.lower().strip()
        cleaned = re.sub(r'[^a-z0-9\s]', ' ', cleaned)
        cleaned = re.sub(r'(.)\1{2,}', r'\1\1', cleaned)

        for phrase, replacement in self.lexicon.items():
            if " " in phrase and phrase in cleaned:
                cleaned = cleaned.replace(phrase, replacement)

        tokens = cleaned.split()
        normalized_tokens = [self.lexicon.get(token, token) for token in tokens]

        return " ".join(normalized_tokens)

    def analyze(self, text: str) -> Dict[str, Any]:
        normalized_text = self.normalize_text(text)
        original_words = re.findall(r'\b\w+\b', text.lower())
        
        detected_slangs = []
        matched_categories = []

        for word in original_words:
            if word in self.lexicon:
                detected_slangs.append(word)
                matched_categories.append(self.lexicon[word])

        score = 0.0
        for category in matched_categories:
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
            "detected_slangs": list(set(detected_slangs)),
            "slang_count": len(detected_slangs),
            "mapped_categories": list(set(matched_categories)),
            "risk_score": risk_score,
            "is_suspicious": risk_score >= 0.35,
        }


if __name__ == "__main__":
    detector = HinglishSlangDetector()
    
    print("=" * 50)
    print(" DrugShield AI - Hinglish Slang Classifier Interactive CLI")
    print(" Type 'exit' or 'quit' to close the program.")
    print("=" * 50)

    while True:
        user_text = input("\nEnter message to analyze: ").strip()
        
        if user_text.lower() in ["exit", "quit"]:
            print("Exiting classifier...")
            break
            
        if not user_text:
            print("Please enter a valid message.")
            continue

        res = detector.analyze(user_text)
        
        print("\n" + "-" * 40)
        print(" ANALYSIS RESULT")
        print("-" * 40)
        print(f"Original Text   : {res['original_text']}")
        print(f"Normalized Text : {res['normalized_text']}")
        print(f"Detected Slangs : {res['detected_slangs']}")
        print(f"Mapped Topics   : {res['mapped_categories']}")
        print(f"Risk Score      : {res['risk_score']}")
        print(f"Suspicious      : {'🚨 YES' if res['is_suspicious'] else '✅ NO'}")
        print("-" * 40)