# config/constants.py
"""
DrugShield AI - Central Intelligence Taxonomy & Constants
Comprehensive narcotics dictionaries, street slang lexicons,
solicitation keywords, and regex patterns for threat detection.
"""

# ==============================================================================
# 1. REGEX PATTERNS FOR OSINT ENTITY EXTRACTION
# ==============================================================================
REGEX_PATTERNS = {
    "UPI_VPA": r"[a-zA-Z0-9.\-_]+@[a-zA-Z]{3,}",
    "PHONE": r"(?:\+?91[\-\s]?)?[6-9]\d{9}",
    "TELEGRAM_LINK": r"(?:https?://)?(?:t\.me|telegram\.me)/[a-zA-Z0-9_]+",
    "TELEGRAM_BOT": r"(?:https?://)?(?:t\.me|telegram\.me)/[a-zA-Z0-9_]*bot\b|@[a-zA-Z0-9_]*bot\b",
    "WHATSAPP_LINK": r"(?:https?://)?(?:chat\.whatsapp\.com|wa\.me)/[a-zA-Z0-9_\-]+",
    "WICKR_HANDLE": r"\b(?:wickr(?:\.me/|:|\s*(?:id|handle)?[:\s]+[a-zA-Z0-9_\-]+))\b",
    "SIGNAL_HANDLE": r"\b(?:signal(?:\.me/[a-zA-Z0-9_\-#\?]+|(?:\s*(?:id|handle)?[:\s]+[a-zA-Z0-9_\.\+]+)))\b",
    "DARKNET_ONION": r"\b[a-zA-Z0-9\-]+\.onion\b",
    "GEO_COORDINATES": r"[-+]?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?),\s*[-+]?(?:180(?:\.0+)?|(?:1[0-7]\d|[1-9]?\d)(?:\.\d+)?)",
    "SESSION_ID": r"\b05[0-9a-fA-F]{64}\b",
    "CRYPTO_BITCOIN": r"\b(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,39}\b",
    "CRYPTO_ETHEREUM": r"\b0x[a-fA-F0-9]{40}\b",
    "CRYPTO_MONERO": r"\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b",
}

# ==============================================================================
# 2. CATEGORIZED NARCOTICS & CONTROLLED SUBSTANCES TAXONOMY
# ==============================================================================
NARCOTICS_TAXONOMY = {
    "cannabis": [
        "weed", "marijuana", "ganja", "cannabis", "charas", "hash", "hashish",
        "pot", "bhang", "mary jane", "joint", "blunt", "bud", "buds",
        "thc", "cbd", "shatter", "wax", "skunk", "og kush", "hydro", "malana cream",
        "indica", "sativa", "dabs", "edibles", "greens", "green"
    ],
    "opioids": [
        "heroin", "chitta", "smack", "brown sugar", "morphine", "fentanyl",
        "tramadol", "codeine", "oxycodone", "oxycontin", "methadone", "buprenorphine",
        "opium", "afeem", "doda", "chitta powder"
    ],
    "stimulants": [
        "cocaine", "coke", "blow", "snow", "crack", "mephedrone", "m-cat",
        "meow meow", "mdma", "molly", "ecstasy", "xtc", "meth", "methamphetamine",
        "crystal meth", "ice", "speed", "amphetamine", "m-kat", "white sugar"
    ],
    "psychedelics": [
        "lsd", "acid", "blotter", "blotters", "stamp", "stamps", "magic mushroom",
        "shrooms", "psilocybin", "dmt", "ayahuasca", "mescaline", "2c-b", "nbome",
        "ketamine", "special k", "k-hole", "salvia"
    ],
    "pharmaceutical_sedatives": [
        "alprazolam", "xanax", "valium", "diazepam", "clonazepam", "ativan",
        "lorazepam", "zolpidem", "nitrazepam", "rohypnol", "roofies",
        "lean", "purple drank", "cough syrup"
    ],
    "synthetic_designer": [
        "synthetic cannabinoid", "k2", "spice", "bath salts", "flakka",
        "ghb", "gbl", "designer drug"
    ]
}

# Flattened set of all known drug substance terms (lowercase)
ALL_DRUG_NAMES = set()
for category, terms in NARCOTICS_TAXONOMY.items():
    for term in terms:
        ALL_DRUG_NAMES.add(term.lower())

# ==============================================================================
# 3. SOLICITATION & DEALING CONTEXT KEYWORDS
# ==============================================================================
SOLICITATION_KEYWORDS = [
    # Action / Purchase terms
    "score", "stash", "plug", "dealer", "vendor", "supplies", "stuff",
    "delivery", "direct delivery", "drop", "dead drop", "drop pin", "drop point",
    "gps pin", "pin drop", "token", "token amount", "advance",
    "stock", "fresh stock", "pure", "pure stuff", "hq", "pure quality",
    "rates", "rate list", "price list", "menu", "stealth", "vacuum sealed",
    
    # Quantities & units
    "1g", "2g", "3g", "5g", "10g", "gram", "grams", "gm", "half gm",
    "ounce", "oz", "pills", "tabs", "capsules", "sheet", "vial", "packet", "pouch",
    
    # Financial / Contact hints
    "upi accepted", "crypto only", "cash on drop", "dm to buy", "dm for order",
    "contact plug", "order here", "secret chat"
]

# High-priority single token indicators
HIGH_PRIORITY_DRUG_TOKENS = {
    "mdma", "lsd", "chitta", "heroin", "cocaine", "coke", "mephedrone", "meth",
    "ganja", "charas", "weed", "blotter", "fentanyl", "ketamine", "molly", "ecstasy"
}

# ==============================================================================
# 4. RISK SCORING WEIGHTS
# ==============================================================================
RISK_WEIGHTS = {
    "PRIMARY_DRUG_MATCH": 0.40,
    "SECONDARY_DRUG_MATCH": 0.25,
    "SOLICITATION_INTENT": 0.20,
    "FINANCIAL_VPA_ATTACHED": 0.15,
    "IMAGE_CONTRABAND_DETECTED": 0.35,
}

# Risk level thresholds
RISK_THRESHOLDS = {
    "CRITICAL": 0.75,
    "HIGH": 0.50,
    "MEDIUM": 0.30,
    "LOW": 0.15,
}

# ==============================================================================
# 5. QR FORENSIC THREAT CLASSIFICATION CONSTANTS
# ==============================================================================
STATUS_DRUG_DETECTED = "DRUG_DETECTED"
STATUS_SUSPICIOUS = "SUSPICIOUS"
STATUS_CLEAN = "CLEAN"

# Specific controlled pharmaceuticals / prescription narcotics
CONTROLLED_PHARMACEUTICAL_PILLS = [
    "xanax", "alprazolam", "valium", "diazepam", "clonazepam", "ativan",
    "lorazepam", "zolpidem", "nitrazepam", "rohypnol", "adderall",
    "percocet", "tramadol", "oxycodone", "oxycontin", "hydrocodone",
    "vicodin", "suboxone", "buprenorphine"
]

# Pill-related generic tokens
GENERIC_PILL_KEYWORDS = [
    "pill", "pills", "tablet", "tablets", "capsule", "capsules",
    "pressies", "bars", "beans", "sheet", "vial", "blotters", "stamps"
]

# Known contraband menu & dealing phrases
CONTRABAND_MENU_PHRASES = [
    "menu", "rate list", "price list", "rates", "stealth delivery",
    "vacuum sealed", "cash on drop", "dm to buy", "dm for order",
    "order here", "fresh stock", "pure stuff", "pure quality",
    "hq stuff", "rave supplies", "contraband"
]

# Obfuscated drug slangs & street jargon
OBFUSCATED_DRUG_SLANGS = [
    "chitta", "ice", "snow", "blow", "white sugar", "meow meow",
    "m-cat", "special k", "lean", "purple drank", "plug", "score",
    "stash", "greens", "dabs", "gear", "smack", "molly", "xtc",
    "acid", "blotters", "stamps", "shrooms", "420", "cid", "lucy",
    "snow white", "m-kat", "bhang", "pot", "bud", "buds", "afeem",
    "doda", "charas", "hashish", "joint", "blunt"
]

# Dead-drop delivery indicators
DEAD_DROP_KEYWORDS = [
    "dead drop", "drop pin", "pin drop", "gps pin", "drop point",
    "drop location", "cash on drop", "dead-drop", "drop coordinates"
]

# Encrypted redirect indicators
ENCRYPTED_REDIRECT_KEYWORDS = [
    "telegram bot", "wickr", "signal", "session id", "simplex",
    "darknet", "onion", "tor", "secret chat", "t.me"
]
