"""
DrugShield AI - Module 2: OCR Parser & Image Forensics Engine
============================================================
Processes media evidence (rate cards, menus, payment screenshots)
stored in `data/raw/images/` using OpenCV image preprocessing and
Tesseract OCR to extract narcotics solicitation text and financial identifiers.
"""

import os
import re
import cv2
import sys
from pathlib import Path

# Path Resolution
FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent.parent
PROJECT_ROOT = SRC_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None

from config.constants import REGEX_PATTERNS, ALL_DRUG_NAMES, SOLICITATION_KEYWORDS


def preprocess_image(image_path: str):
    """
    Applies OpenCV preprocessing pipeline:
    Grayscale conversion, Gaussian blur, and adaptive thresholding to maximize OCR contrast.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return None

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Noise removal with bilateral filter (preserves edges)
    denoised = cv2.bilateralFilter(gray, 9, 75, 75)

    # Adaptive Otsu thresholding
    _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return thresh


def extract_text_from_image(image_path: str) -> dict:
    """
    Runs OpenCV preprocessing followed by PyTesseract OCR.
    Extracts text, UPI IDs, phone numbers, and narcotics keywords.
    """
    path_obj = Path(image_path)
    if not path_obj.is_file():
        return {
            "success": False,
            "error": f"Image file not found: {image_path}",
            "text": ""
        }

    extracted_text = ""

    if pytesseract:
        try:
            processed_cv = preprocess_image(str(path_obj))
            if processed_cv is not None:
                extracted_text = pytesseract.image_to_string(processed_cv)
            else:
                extracted_text = pytesseract.image_to_string(Image.open(path_obj))
        except Exception as e:
            # Fallback if tesseract binary is not installed in system PATH
            extracted_text = f"[OCR Notice] OCR engine offline or binary not in PATH: {e}"

    # Extract Entities via Regex
    upi_matches = re.findall(REGEX_PATTERNS.get("UPI_VPA", r"[a-zA-Z0-9.\-_]+@[a-zA-Z]{3,}"), extracted_text)
    phone_matches = re.findall(REGEX_PATTERNS.get("PHONE", r"(?:\+?91[\-\s]?)?[6-9]\d{9}"), extracted_text)

    # Scan for drug keywords
    lower_text = extracted_text.lower()
    detected_drugs = [term for term in ALL_DRUG_NAMES if re.search(r"\b" + re.escape(term) + r"\b", lower_text)]
    detected_solicitation = [term for term in SOLICITATION_KEYWORDS if re.search(r"\b" + re.escape(term) + r"\b", lower_text)]

    return {
        "success": True,
        "image_path": str(path_obj),
        "raw_text": extracted_text.strip(),
        "extracted_upi": list(set(upi_matches)),
        "extracted_phones": list(set(phone_matches)),
        "detected_drugs": list(set(detected_drugs)),
        "detected_solicitation": list(set(detected_solicitation)),
        "is_threat": len(detected_drugs) > 0 or len(upi_matches) > 0
    }


if __name__ == "__main__":
    test_img = PROJECT_ROOT / "data" / "raw" / "sample_menu.jpg"
    print(f"[*] Testing OCR parser on: {test_img}")
    res = extract_text_from_image(str(test_img))
    print(json.dumps(res, indent=2))
