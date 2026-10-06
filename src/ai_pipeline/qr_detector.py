# src/ai_pipeline/qr_detector.py
"""
DrugShield AI - Module 2: QR Detection, Threat Analysis & Forensic Extraction Pipeline
======================================================================================
Capabilities:
1. Multi-Engine QR Code Detection:
   - YOLOv8 localized bounding box detection via `src/ai_pipeline/models/qr_detector.pt`
   - High-res crop extraction with fallback to OpenCV (cv2.QRCodeDetector) and PyZBar
   - Computer vision preprocessing variants (CLAHE, Otsu threshold, sharpening)
2. Intelligent Payload Decoding:
   - Extracts raw text, URLs, NPCI UPI payment schemes, contact cards (vCard), crypto
3. Narcotics & Solicitation Threat Analysis:
   - DRUG_DETECTED: Explicit illicit substance names (MDMA, Meth, Weed, Cocaine, Tramadol,
     scheduled pills) or contraband menu phrases
   - SUSPICIOUS: Obfuscated drug slangs, encrypted contact redirects (Telegram bots,
     Wickr/Signal, Darknet .onion mirrors, dead-drop coordinates), or pill-related keywords
   - CLEAN / BENIGN: No narcotics or illicit solicitation patterns identified
4. Forensic Evidence Archiving:
   - Caches cropped QR code artifacts into `data/forensic_cache/qr_crops/`
   - Appends structured forensic intelligence dossiers into `data/qr_deep_intel.json`
5. Pipeline Hook:
   - Clean runner function `scan_qr_payload(image_path: str) -> dict`
"""

import os
import sys
import re
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime, timezone

# Ensure headless-safe OpenCV environment
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"

# Windows DLL directory hook for PyZBar / ZBar binaries
if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    py_dir = Path(sys.executable).parent
    for candidate in [py_dir, py_dir / "Library" / "bin", py_dir / "DLLs"]:
        if candidate.is_dir():
            try:
                os.add_dll_directory(str(candidate))
            except Exception:
                pass

import cv2
import numpy as np
from PIL import Image

# Import PyZBar if available
try:
    from pyzbar import pyzbar
    from pyzbar.pyzbar import ZBarSymbol
    PYZBAR_AVAILABLE = True
except (ImportError, Exception):
    PYZBAR_AVAILABLE = False
    pyzbar = None
    ZBarSymbol = None

# Import Ultralytics YOLO if available
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    YOLO = None

# Path Resolution & Sys Path Hook
FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent.parent
PROJECT_ROOT = SRC_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Logger Setup
logger = logging.getLogger("DrugShield.QRDetector")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [DrugShield-QR] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Import Taxonomy & Constants
try:
    from config.constants import (
        NARCOTICS_TAXONOMY,
        ALL_DRUG_NAMES,
        SOLICITATION_KEYWORDS,
        HIGH_PRIORITY_DRUG_TOKENS,
        REGEX_PATTERNS,
        STATUS_DRUG_DETECTED,
        STATUS_SUSPICIOUS,
        STATUS_CLEAN,
        CONTROLLED_PHARMACEUTICAL_PILLS,
        GENERIC_PILL_KEYWORDS,
        CONTRABAND_MENU_PHRASES,
        OBFUSCATED_DRUG_SLANGS,
        DEAD_DROP_KEYWORDS,
        ENCRYPTED_REDIRECT_KEYWORDS,
    )
except ImportError:
    # Standalone Fallback Constants
    STATUS_DRUG_DETECTED = "DRUG_DETECTED"
    STATUS_SUSPICIOUS = "SUSPICIOUS"
    STATUS_CLEAN = "CLEAN"

    NARCOTICS_TAXONOMY = {
        "cannabis": ["weed", "marijuana", "ganja", "cannabis", "charas", "hash", "hashish", "thc", "cbd", "og kush"],
        "opioids": ["heroin", "chitta", "smack", "brown sugar", "morphine", "fentanyl", "tramadol", "codeine", "oxycodone"],
        "stimulants": ["cocaine", "coke", "crack", "mephedrone", "m-cat", "mdma", "molly", "ecstasy", "meth", "crystal meth"],
        "psychedelics": ["lsd", "acid", "blotter", "stamp", "shrooms", "psilocybin", "ketamine", "dmt"],
        "pharmaceutical_sedatives": ["alprazolam", "xanax", "valium", "diazepam", "clonazepam", "lean"],
    }
    ALL_DRUG_NAMES = {t.lower() for terms in NARCOTICS_TAXONOMY.values() for t in terms}
    SOLICITATION_KEYWORDS = [
        "score", "stash", "plug", "dealer", "vendor", "delivery", "drop", "dead drop",
        "stock", "pure", "rates", "rate list", "menu", "stealth", "1g", "5g", "dm to buy"
    ]
    HIGH_PRIORITY_DRUG_TOKENS = {"mdma", "lsd", "chitta", "heroin", "cocaine", "coke", "meth", "weed", "ganja"}
    CONTROLLED_PHARMACEUTICAL_PILLS = [
        "xanax", "alprazolam", "valium", "diazepam", "clonazepam", "ativan",
        "lorazepam", "zolpidem", "nitrazepam", "rohypnol", "adderall",
        "percocet", "tramadol", "oxycodone", "oxycontin"
    ]
    GENERIC_PILL_KEYWORDS = ["pill", "pills", "tablet", "tablets", "capsule", "capsules", "pressies", "bars", "beans"]
    CONTRABAND_MENU_PHRASES = [
        "menu", "rate list", "price list", "rates", "stealth delivery",
        "vacuum sealed", "cash on drop", "dm to buy", "dm for order",
        "order here", "fresh stock", "pure stuff", "pure quality"
    ]
    OBFUSCATED_DRUG_SLANGS = [
        "chitta", "ice", "snow", "blow", "white sugar", "meow meow",
        "m-cat", "special k", "lean", "plug", "score", "stash", "greens",
        "dabs", "gear", "smack", "molly", "xtc", "acid", "blotters", "stamps"
    ]
    DEAD_DROP_KEYWORDS = ["dead drop", "drop pin", "pin drop", "gps pin", "drop point", "drop location", "cash on drop"]
    ENCRYPTED_REDIRECT_KEYWORDS = ["telegram bot", "wickr", "signal", "session id", "simplex", "darknet", "onion", "tor"]
    REGEX_PATTERNS = {
        "UPI_VPA": r"[a-zA-Z0-9.\-_]+@[a-zA-Z]{3,}",
        "PHONE": r"(?:\+?91[\-\s]?)?[6-9]\d{9}",
        "TELEGRAM_BOT": r"(?:https?://)?(?:t\.me|telegram\.me)/[a-zA-Z0-9_]*bot\b|@[a-zA-Z0-9_]*bot\b",
        "WICKR_HANDLE": r"\b(?:wickr(?:\.me/|:|\s*(?:id|handle)?[:\s]+[a-zA-Z0-9_\-]+))\b",
        "SIGNAL_HANDLE": r"\b(?:signal(?:\.me/[a-zA-Z0-9_\-#\?]+|(?:\s*(?:id|handle)?[:\s]+[a-zA-Z0-9_\.\+]+)))\b",
        "DARKNET_ONION": r"\b[a-zA-Z0-9\-]+\.onion\b",
        "GEO_COORDINATES": r"[-+]?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?),\s*[-+]?(?:180(?:\.0+)?|(?:1[0-7]\d|[1-9]?\d)(?:\.\d+)?)",
        "SESSION_ID": r"\b05[0-9a-fA-F]{64}\b",
    }

# NLP Classifier Import
try:
    from src.ai_pipeline.nlp_classifier import NLPNarcoticsClassifier
except ImportError:
    NLPNarcoticsClassifier = None

# Default Paths
DEFAULT_YOLO_MODEL_PATH = FILE_PATH.parent / "models" / "qr_detector.pt"
DEFAULT_INTEL_PATH = PROJECT_ROOT / "data" / "qr_deep_intel.json"
DEFAULT_CROPS_DIR = PROJECT_ROOT / "data" / "forensic_cache" / "qr_crops"


# ==============================================================================
# FORENSIC UTILITIES
# ==============================================================================
def compute_sha256(data_or_path: Union[bytes, str, Path]) -> str:
    """Calculate cryptographic SHA-256 hash for forensic chain-of-custody."""
    hasher = hashlib.sha256()
    if isinstance(data_or_path, (str, Path)):
        p = Path(data_or_path)
        if not p.is_file():
            return "FILE_NOT_FOUND"
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
    elif isinstance(data_or_path, bytes):
        hasher.update(data_or_path)
    return hasher.hexdigest()


def generate_evidence_id(prefix: str = "DS-QR") -> str:
    """Generate standardized law-enforcement evidence identifier."""
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand_hex = hashlib.md5(f"{time.time()}_{os.getpid()}".encode()).hexdigest()[:6].upper()
    return f"{prefix}-{now_str}-{rand_hex}"


# ==============================================================================
# QR THREAT DETECTOR CLASS
# ==============================================================================
class QRThreatDetector:
    """
    Forensic QR Detector and Narcotics Threat Analyzer.
    Combines YOLOv8 localized detection, PyZBar/OpenCV decoding,
    and multi-tiered threat intelligence evaluation.
    """

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        intel_output_path: Optional[Union[str, Path]] = None,
        crops_dir: Optional[Union[str, Path]] = None,
        confidence_threshold: float = 0.20,
    ):
        self.model_path = Path(model_path) if model_path else DEFAULT_YOLO_MODEL_PATH
        self.intel_output_path = Path(intel_output_path) if intel_output_path else DEFAULT_INTEL_PATH
        self.crops_dir = Path(crops_dir) if crops_dir else DEFAULT_CROPS_DIR
        self.confidence_threshold = confidence_threshold

        # Initialize directories
        self.crops_dir.mkdir(parents=True, exist_ok=True)
        self.intel_output_path.parent.mkdir(parents=True, exist_ok=True)

        # NLP Classifier Instance
        if NLPNarcoticsClassifier is not None:
            self.nlp_classifier = NLPNarcoticsClassifier()
        else:
            self.nlp_classifier = None

        # OpenCV QRCodeDetector
        self.opencv_detector = cv2.QRCodeDetector()

        # Lazy load YOLO model
        self._yolo_model: Optional[Any] = None
        self._yolo_initialized = False

        # Precompile Threat Inspection Regexes
        self._compile_regexes()

    def _compile_regexes(self):
        """Compile fast search regex patterns for threat evaluation."""
        self.re_telegram_bot = re.compile(
            r"(?:https?://)?(?:t\.me|telegram\.me)/[a-zA-Z0-9_]*bot\b|@[a-zA-Z0-9_]*bot\b",
            re.IGNORECASE,
        )
        self.re_wickr = re.compile(
            r"\b(?:wickr(?:\.me/|:|\s*(?:id|handle)?[:\s]+[a-zA-Z0-9_\-]+))\b",
            re.IGNORECASE,
        )
        self.re_signal = re.compile(
            r"\b(?:signal(?:\.me/[a-zA-Z0-9_\-#\?]+|(?:\s*(?:id|handle)?[:\s]+[a-zA-Z0-9_\.\+]+)))\b",
            re.IGNORECASE,
        )
        self.re_onion = re.compile(r"\b[a-zA-Z0-9\-]+\.onion\b", re.IGNORECASE)
        self.re_coords = re.compile(
            r"[-+]?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?),\s*[-+]?(?:180(?:\.0+)?|(?:1[0-7]\d|[1-9]?\d)(?:\.\d+)?)"
        )
        self.re_session = re.compile(r"\b05[0-9a-fA-F]{64}\b")

        # Explicit drug tokens (lowercase set)
        self.explicit_drugs = set(ALL_DRUG_NAMES)
        for cat, items in NARCOTICS_TAXONOMY.items():
            for itm in items:
                self.explicit_drugs.add(itm.lower())

        # Controlled pills
        self.controlled_pills = {p.lower() for p in CONTROLLED_PHARMACEUTICAL_PILLS}

        # Generic pills
        self.generic_pills = {p.lower() for p in GENERIC_PILL_KEYWORDS}

        # Contraband menu phrases
        self.menu_phrases = [p.lower() for p in CONTRABAND_MENU_PHRASES]

        # Obfuscated slangs
        self.obfuscated_slangs = {s.lower() for s in OBFUSCATED_DRUG_SLANGS}

        # Dead drop keywords
        self.dead_drop_keywords = [k.lower() for k in DEAD_DROP_KEYWORDS]

    def _get_yolo_model(self) -> Optional[Any]:
        """Lazy loader for YOLOv8 QR detection model."""
        if not self._yolo_initialized:
            self._yolo_initialized = True
            if YOLO_AVAILABLE and self.model_path.is_file():
                try:
                    logger.info(f"Loading YOLOv8 QR detector model from {self.model_path}...")
                    self._yolo_model = YOLO(str(self.model_path))
                    logger.info("YOLOv8 QR detector model loaded successfully.")
                except Exception as e:
                    logger.warning(f"Could not load YOLO model from {self.model_path}: {e}")
                    self._yolo_model = None
            else:
                if not self.model_path.is_file():
                    logger.info(f"YOLO weights not found at {self.model_path}. Using OpenCV/PyZBar fallbacks.")
                self._yolo_model = None
        return self._yolo_model

    # --------------------------------------------------------------------------
    # IMAGE LOADING & PREPROCESSING
    # --------------------------------------------------------------------------
    def _load_image(self, image_input: Union[str, Path, np.ndarray, Image.Image]) -> Tuple[Optional[np.ndarray], Optional[Path]]:
        """Load image into BGR numpy matrix and return with resolved Path if available."""
        if isinstance(image_input, (str, Path)):
            p = Path(image_input)
            if not p.is_file():
                return None, None
            try:
                with open(p, "rb") as f:
                    arr = np.frombuffer(f.read(), dtype=np.uint8)
                    mat = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    return mat, p
            except Exception as e:
                logger.error(f"Failed to read image from {p}: {e}")
                return None, p
        elif isinstance(image_input, np.ndarray):
            return image_input, None
        elif isinstance(image_input, Image.Image):
            rgb = image_input.convert("RGB")
            return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR), None
        return None, None

    def _generate_enhanced_variants(self, img_bgr: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        """Generate computer vision enhancements for low-contrast/compressed QR codes."""
        variants = []
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if len(img_bgr.shape) == 3 else img_bgr.copy()

        # CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        variants.append(("clahe", clahe.apply(gray)))

        # Otsu Binary Thresholding
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(("otsu", otsu))

        # Sharpening
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        sharpened = cv2.filter2D(gray, -1, kernel)
        variants.append(("sharpened", sharpened))

        # Inverted Threshold
        variants.append(("inverted", cv2.bitwise_not(gray)))

        return variants

    # --------------------------------------------------------------------------
    # LOW-LEVEL DECODING IMPLEMENTATIONS
    # --------------------------------------------------------------------------
    def _decode_mat_pyzbar(self, img_mat: np.ndarray) -> List[Dict[str, Any]]:
        """Decode with PyZBar on an image matrix."""
        results = []
        if not PYZBAR_AVAILABLE or pyzbar is None:
            return results

        try:
            symbols = [ZBarSymbol.QRCODE] if ZBarSymbol is not None else []
            decoded_objects = pyzbar.decode(img_mat, symbols=symbols) if symbols else pyzbar.decode(img_mat)
            for obj in decoded_objects:
                try:
                    payload = obj.data.decode("utf-8").strip()
                except UnicodeDecodeError:
                    payload = obj.data.decode("latin-1", errors="ignore").strip()

                if not payload:
                    continue

                rect = obj.rect
                bbox = [int(rect.left), int(rect.top), int(rect.width), int(rect.height)]
                results.append({
                    "payload": payload,
                    "engine": "pyzbar",
                    "bbox": bbox,
                })
        except Exception as e:
            logger.debug(f"PyZBar decode error: {e}")
        return results

    def _decode_mat_opencv(self, img_mat: np.ndarray) -> List[Dict[str, Any]]:
        """Decode with OpenCV QRCodeDetector."""
        results = []
        try:
            gray = cv2.cvtColor(img_mat, cv2.COLOR_BGR2GRAY) if len(img_mat.shape) == 3 else img_mat

            if hasattr(self.opencv_detector, "detectAndDecodeMulti"):
                success, decoded_info, points, _ = self.opencv_detector.detectAndDecodeMulti(gray)
                if success and decoded_info:
                    for i, text in enumerate(decoded_info):
                        text = text.strip() if text else ""
                        if not text:
                            continue
                        pts = points[i].tolist() if points is not None and len(points) > i else []
                        bbox = self._pts_to_bbox(pts)
                        results.append({
                            "payload": text,
                            "engine": "opencv_multi",
                            "bbox": bbox,
                        })

            if not results:
                text, points, _ = self.opencv_detector.detectAndDecode(gray)
                text = text.strip() if text else ""
                if text:
                    pts = points.tolist() if points is not None else []
                    results.append({
                        "payload": text,
                        "engine": "opencv_single",
                        "bbox": self._pts_to_bbox(pts),
                    })
        except Exception as e:
            logger.debug(f"OpenCV decode error: {e}")
        return results

    def _pts_to_bbox(self, pts: List[Any]) -> List[int]:
        """Convert polygon points to [x, y, w, h] bounding box."""
        if not pts:
            return [0, 0, 0, 0]
        try:
            pts_arr = np.array(pts, dtype=np.int32).reshape(-1, 2)
            x, y, w, h = cv2.boundingRect(pts_arr)
            return [int(x), int(y), int(w), int(h)]
        except Exception:
            return [0, 0, 0, 0]

    def _decode_crop_or_image(self, mat: np.ndarray) -> Optional[Tuple[str, str, List[int]]]:
        """
        Attempts decoding with PyZBar and OpenCV across raw and enhanced variants.
        Returns (payload, engine_name, bbox) or None.
        """
        # 1. Direct PyZBar
        if PYZBAR_AVAILABLE:
            zbar_res = self._decode_mat_pyzbar(mat)
            if zbar_res:
                return zbar_res[0]["payload"], "pyzbar", zbar_res[0]["bbox"]

        # 2. Direct OpenCV
        cv_res = self._decode_mat_opencv(mat)
        if cv_res:
            return cv_res[0]["payload"], cv_res[0]["engine"], cv_res[0]["bbox"]

        # 3. Enhanced Variants
        variants = self._generate_enhanced_variants(mat)
        for var_name, var_mat in variants:
            if PYZBAR_AVAILABLE:
                z_res = self._decode_mat_pyzbar(var_mat)
                if z_res:
                    return z_res[0]["payload"], f"pyzbar+{var_name}", z_res[0]["bbox"]

            c_res = self._decode_mat_opencv(var_mat)
            if c_res:
                return c_res[0]["payload"], f"opencv+{var_name}", c_res[0]["bbox"]

        return None

    # --------------------------------------------------------------------------
    # DETECTION ENGINE: YOLO LOCALIZATION + OPENCV/PYZBAR FALLBACK
    # --------------------------------------------------------------------------
    def detect_and_decode(self, img_bgr: np.ndarray, source_hash: str) -> List[Dict[str, Any]]:
        """
        Executes dual-layer QR detection and decoding:
        1. YOLO localized bounding box detection (crops QR region and decodes)
        2. Fallback to full-image PyZBar and OpenCV detection
        Caches cropped QR artifacts to `data/forensic_cache/qr_crops/`.
        """
        h, w = img_bgr.shape[:2]
        decoded_items = []
        seen_payloads = set()

        yolo_model = self._get_yolo_model()

        # Phase 1: YOLO localized detection
        if yolo_model is not None:
            try:
                yolo_results = yolo_model.predict(
                    source=img_bgr,
                    conf=self.confidence_threshold,
                    verbose=False,
                    device="cpu"
                )

                for r in yolo_results:
                    if not hasattr(r, "boxes") or r.boxes is None:
                        continue

                    # Filter for qrcode class (cls 1 or name containing 'qr')
                    for box in r.boxes:
                        cls_id = int(box.cls[0].item())
                        cls_name = yolo_model.names.get(cls_id, "").lower()
                        conf = float(box.conf[0].item())

                        # Check if qrcode class (either class id 1 or name 'qrcode')
                        is_qr_class = ("qr" in cls_name) or (cls_id == 1)
                        if not is_qr_class:
                            continue

                        xyxy = box.xyxy[0].tolist()
                        x1 = max(0, int(xyxy[0]))
                        y1 = max(0, int(xyxy[1]))
                        x2 = min(w, int(xyxy[2]))
                        y2 = min(h, int(xyxy[3]))

                        # Add 12% padding for safe finder pattern inclusion
                        pad_w = int((x2 - x1) * 0.12)
                        pad_h = int((y2 - y1) * 0.12)
                        crop_x1 = max(0, x1 - pad_w)
                        crop_y1 = max(0, y1 - pad_h)
                        crop_x2 = min(w, x2 + pad_w)
                        crop_y2 = min(h, y2 + pad_h)

                        crop_mat = img_bgr[crop_y1:crop_y2, crop_x1:crop_x2]
                        if crop_mat.size == 0:
                            continue

                        decoded = self._decode_crop_or_image(crop_mat)
                        if decoded:
                            payload, engine_name, _ = decoded
                            if payload and payload not in seen_payloads:
                                seen_payloads.add(payload)
                                crop_path = self._save_crop(crop_mat, source_hash, len(decoded_items))
                                decoded_items.append({
                                    "payload": payload,
                                    "bbox": [crop_x1, crop_y1, crop_x2 - crop_x1, crop_y2 - crop_y1],
                                    "crop_path": str(crop_path.resolve()) if crop_path else None,
                                    "engine": f"yolo_v8({conf:.2f})+{engine_name}",
                                })
            except Exception as e:
                logger.warning(f"YOLO QR localization exception: {e}")

        # Phase 2: Fallback to full-image PyZBar and OpenCV if no QR decoded yet
        if not decoded_items:
            decoded = self._decode_crop_or_image(img_bgr)
            if decoded:
                payload, engine_name, bbox = decoded
                if payload and payload not in seen_payloads:
                    seen_payloads.add(payload)
                    # Compute crop from bbox if valid
                    x, y, bw, bh = bbox
                    if bw > 0 and bh > 0:
                        crop_x1 = max(0, x - int(bw * 0.10))
                        crop_y1 = max(0, y - int(bh * 0.10))
                        crop_x2 = min(w, x + bw + int(bw * 0.10))
                        crop_y2 = min(h, y + bh + int(bh * 0.10))
                        crop_mat = img_bgr[crop_y1:crop_y2, crop_x1:crop_x2]
                    else:
                        crop_mat = img_bgr

                    crop_path = self._save_crop(crop_mat, source_hash, len(decoded_items))
                    decoded_items.append({
                        "payload": payload,
                        "bbox": bbox if (bw > 0 and bh > 0) else [0, 0, w, h],
                        "crop_path": str(crop_path.resolve()) if crop_path else None,
                        "engine": f"fallback_{engine_name}",
                    })

        return decoded_items

    def _save_crop(self, crop_mat: np.ndarray, source_hash: str, index: int) -> Optional[Path]:
        """Save cropped QR artifact to forensic cache directory."""
        try:
            timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            short_hash = source_hash[:10] if source_hash != "FILE_NOT_FOUND" else "live"
            crop_filename = f"qr_crop_{short_hash}_{timestamp_str}_{index}.png"
            target_path = self.crops_dir / crop_filename

            # Save PNG losslessly
            cv2.imwrite(str(target_path), crop_mat)
            logger.info(f"Cached cropped QR artifact: {target_path.resolve()}")
            return target_path
        except Exception as e:
            logger.error(f"Failed to save cropped QR artifact: {e}")
            return None

    # --------------------------------------------------------------------------
    # THREAT EVALUATION LOGIC
    # --------------------------------------------------------------------------
    def evaluate_threat(self, payload: str) -> Dict[str, Any]:
        """
        Evaluates a decoded QR payload string for narcotics and illicit solicitation patterns.
        Enforces 3-tier threat taxonomy:
        - DRUG_DETECTED: Explicit illicit substance names or known contraband menu phrases
        - SUSPICIOUS: Obfuscated slangs, encrypted contact redirects (Telegram bots,
                      Wickr/Signal, Darknet .onion mirrors, dead-drop coordinates), or pill keywords
        - CLEAN: No indicators or solicitation patterns matched
        """
        if not payload or not str(payload).strip():
            return {
                "status": STATUS_CLEAN,
                "confidence_score": 0.0,
                "threat_indicators": [],
                "extracted_keywords": [],
            }

        raw_payload = str(payload).strip()

        # Step 1: De-obfuscation
        if self.nlp_classifier is not None:
            deobfuscated_corpus = self.nlp_classifier.deobfuscate(raw_payload)
        else:
            unquoted = unquote(raw_payload).lower()
            decloaked = re.sub(r'(?<=\b[a-z0-9])[.\-_ ](?=[a-z0-9]\b)', '', unquoted)
            deobfuscated_corpus = f"{unquoted} {decloaked}"

        # If UPI payment scheme, unpack banking parameters for deep textual context
        upi_context = ""
        lower_raw = raw_payload.lower()
        if lower_raw.startswith("upi://pay") or ("upi://" in lower_raw and "pa=" in lower_raw):
            try:
                parsed_url = urlparse(raw_payload)
                qs = parse_qs(parsed_url.query, keep_blank_values=True)
                pa = qs.get("pa", [""])[0]
                pn = qs.get("pn", [""])[0]
                tn = qs.get("tn", [""])[0]
                upi_context = f" {pa} {pn} {tn}"
            except Exception:
                pass

        # Create normalized space-separated corpus where punctuation/symbols become spaces
        delimiter_spaced = re.sub(r'[\_\-\.\/\+\&\=\?\:\@\%\,\;]', ' ', raw_payload).lower()
        full_search_text = f"{raw_payload} {deobfuscated_corpus} {delimiter_spaced} {upi_context}".lower()

        # Exclude common benign phrases
        benign_tokens = {
            "folic acid", "citric acid", "amino acid", "salicylic acid",
            "ice cream", "green tea", "dry ice", "flower pot"
        }
        for b_tok in benign_tokens:
            if b_tok in full_search_text:
                full_search_text = full_search_text.replace(b_tok, " ")

        threat_indicators: List[str] = []
        extracted_keywords: List[str] = []

        is_explicit_drug = False
        is_contraband_menu = False
        is_suspicious_redirect = False
        is_obfuscated_slang = False
        is_pill_keyword = False
        is_dead_drop = False

        # ----------------------------------------------------------------------
        # Tier 1 Verification: Explicit Illicit Substance Names
        # ----------------------------------------------------------------------
        matched_explicit_drugs = set()
        for drug_name in self.explicit_drugs:
            # Word boundary regex to prevent substring collisions
            pat = rf"\b{re.escape(drug_name)}\b"
            if re.search(pat, full_search_text):
                matched_explicit_drugs.add(drug_name)

        if matched_explicit_drugs:
            is_explicit_drug = True
            for d in sorted(matched_explicit_drugs):
                extracted_keywords.append(d)
                threat_indicators.append(f"EXPLICIT_SUBSTANCE: {d.upper()}")

        # Check controlled pharmaceutical pills
        matched_pills = set()
        for pill in self.controlled_pills:
            pat = rf"\b{re.escape(pill)}\b"
            if re.search(pat, full_search_text):
                matched_pills.add(pill)

        if matched_pills:
            is_explicit_drug = True
            for p in sorted(matched_pills):
                extracted_keywords.append(p)
                threat_indicators.append(f"CONTROLLED_PHARMACEUTICAL: {p.upper()}")

        # ----------------------------------------------------------------------
        # Tier 1 Verification: Known Contraband Menu Phrases
        # ----------------------------------------------------------------------
        matched_menu_phrases = set()
        for phrase in self.menu_phrases:
            pat = rf"\b{re.escape(phrase)}\b"
            if re.search(pat, full_search_text):
                matched_menu_phrases.add(phrase)

        if matched_menu_phrases:
            is_contraband_menu = True
            for m in sorted(matched_menu_phrases):
                extracted_keywords.append(m)
                threat_indicators.append(f"CONTRABAND_MENU_PHRASE: '{m}'")

        # ----------------------------------------------------------------------
        # Tier 2 Verification: Encrypted Contact Redirects & Darknet Mirrors
        # ----------------------------------------------------------------------
        # A. Darknet Tor .onion mirrors
        onion_matches = self.re_onion.findall(raw_payload)
        if onion_matches:
            is_suspicious_redirect = True
            for om in onion_matches:
                extracted_keywords.append("darknet_onion")
                threat_indicators.append(f"DARKNET_MIRROR: {om}")

        # B. Telegram Bot Redirects
        tg_bot_matches = self.re_telegram_bot.findall(raw_payload)
        if tg_bot_matches:
            is_suspicious_redirect = True
            for tm in tg_bot_matches:
                extracted_keywords.append("telegram_bot")
                threat_indicators.append(f"ENCRYPTED_REDIRECT: Telegram Bot ({tm})")

        # C. Wickr handles / links
        wickr_matches = self.re_wickr.findall(raw_payload)
        if wickr_matches or "wickr" in full_search_text:
            is_suspicious_redirect = True
            extracted_keywords.append("wickr")
            threat_indicators.append("ENCRYPTED_REDIRECT: Wickr Secure Handle")

        # D. Signal handles / links
        signal_matches = self.re_signal.findall(raw_payload)
        if signal_matches or "signal.me" in full_search_text:
            is_suspicious_redirect = True
            extracted_keywords.append("signal")
            threat_indicators.append("ENCRYPTED_REDIRECT: Signal Messenger Channel")

        # E. Session / Simplex IDs
        session_matches = self.re_session.findall(raw_payload)
        if session_matches or "simplex.chat" in full_search_text:
            is_suspicious_redirect = True
            extracted_keywords.append("anonymized_chat")
            threat_indicators.append("ENCRYPTED_REDIRECT: Anonymized Decentralized Session")

        # ----------------------------------------------------------------------
        # Tier 2 Verification: Dead-Drop Coordinates & Geo Pins
        # ----------------------------------------------------------------------
        coords_matches = self.re_coords.findall(raw_payload)
        if coords_matches:
            is_dead_drop = True
            for cm in coords_matches:
                coords_str = f"({cm[0]}, {cm[1]})" if isinstance(cm, tuple) else str(cm)
                extracted_keywords.append("geo_coordinates")
                threat_indicators.append(f"DEAD_DROP_COORDINATES: {coords_str}")

        for dd_kw in self.dead_drop_keywords:
            if re.search(rf"\b{re.escape(dd_kw)}\b", full_search_text):
                is_dead_drop = True
                extracted_keywords.append(dd_kw)
                threat_indicators.append(f"DEAD_DROP_PATTERN: '{dd_kw}'")

        # ----------------------------------------------------------------------
        # Tier 2 Verification: Obfuscated Drug Slangs
        # ----------------------------------------------------------------------
        matched_slangs = set()
        for slang in self.obfuscated_slangs:
            # If already matched as explicit drug, skip
            if slang in matched_explicit_drugs:
                continue
            pat = rf"\b{re.escape(slang)}\b"
            if re.search(pat, full_search_text):
                matched_slangs.add(slang)

        if matched_slangs:
            is_obfuscated_slang = True
            for s in sorted(matched_slangs):
                extracted_keywords.append(s)
                threat_indicators.append(f"OBFUSCATED_SLANG: {s}")

        # ----------------------------------------------------------------------
        # Tier 2 Verification: Generic Pill Keywords
        # ----------------------------------------------------------------------
        matched_pill_kws = set()
        for pkw in self.generic_pills:
            if re.search(rf"\b{re.escape(pkw)}\b", full_search_text):
                matched_pill_kws.add(pkw)

        if matched_pill_kws:
            is_pill_keyword = True
            for pkw in sorted(matched_pill_kws):
                extracted_keywords.append(pkw)
                threat_indicators.append(f"PILL_INDICATOR: '{pkw}'")

        # ----------------------------------------------------------------------
        # NLP Classifier Cross-Validation
        # ----------------------------------------------------------------------
        if self.nlp_classifier is not None:
            try:
                nlp_res = self.nlp_classifier.classify_text(f"{raw_payload} {delimiter_spaced}")
                if nlp_res.get("is_drug_detected"):
                    for n_drug in nlp_res.get("detected_drug_names", []):
                        if n_drug not in extracted_keywords:
                            extracted_keywords.append(n_drug)
                            threat_indicators.append(f"NLP_DRUG_MATCH: {n_drug.upper()}")
                            is_explicit_drug = True

                    for n_sol in nlp_res.get("detected_solicitation_keywords", []):
                        if n_sol not in extracted_keywords:
                            extracted_keywords.append(n_sol)
                            threat_indicators.append(f"NLP_SOLICITATION_TOKEN: '{n_sol}'")

                    if nlp_res.get("risk_score", 0.0) >= 0.70:
                        is_explicit_drug = True
            except Exception as nlp_err:
                logger.debug(f"NLP classification cross-validation note: {nlp_err}")

        # ----------------------------------------------------------------------
        # Decision Matrix & Confidence Calculation
        # ----------------------------------------------------------------------
        extracted_keywords = sorted(list(set(extracted_keywords)))
        threat_indicators = sorted(list(set(threat_indicators)))

        # Rule 1: DRUG_DETECTED
        # Triggered if explicit substance names or known contraband menu phrases are found
        if is_explicit_drug or is_contraband_menu:
            status = STATUS_DRUG_DETECTED
            base_conf = 0.88
            bonus = min(0.11, (len(extracted_keywords) - 1) * 0.03)
            confidence_score = round(min(0.99, base_conf + bonus), 2)

        # Rule 2: SUSPICIOUS
        # Triggered if obfuscated drug slangs, encrypted contact redirects, dead drops, or pills
        elif is_suspicious_redirect or is_obfuscated_slang or is_dead_drop or is_pill_keyword:
            status = STATUS_SUSPICIOUS
            base_conf = 0.55
            bonus = min(0.24, (len(extracted_keywords) - 1) * 0.05)
            confidence_score = round(min(0.79, base_conf + bonus), 2)

        # Rule 3: CLEAN / BENIGN
        else:
            status = STATUS_CLEAN
            confidence_score = 0.0
            extracted_keywords = []
            threat_indicators = []

        return {
            "status": status,
            "confidence_score": confidence_score,
            "threat_indicators": threat_indicators,
            "extracted_keywords": extracted_keywords,
        }

    # --------------------------------------------------------------------------
    # FULL SCAN EXECUTION & DOSSIER EXPORT
    # --------------------------------------------------------------------------
    def scan(self, image_path: Union[str, Path, np.ndarray, Image.Image]) -> Dict[str, Any]:
        """
        Complete forensic scan pipeline for an image:
        1. Loads image and computes SHA-256 hash
        2. Detects and decodes QR codes (YOLO + PyZBar/OpenCV)
        3. Caches cropped QR artifacts
        4. Analyzes narcotics/solicitation threats
        5. Persists intelligence record into `data/qr_deep_intel.json`
        6. Returns structured scan dictionary
        """
        img_mat, p_path = self._load_image(image_path)
        source_name = str(p_path) if p_path else "in_memory_image"
        source_hash = compute_sha256(p_path) if (p_path and p_path.is_file()) else "IN_MEMORY"
        evidence_id = generate_evidence_id()
        timestamp = datetime.now(timezone.utc).isoformat()

        if img_mat is None:
            logger.warning(f"Could not load image: {source_name}")
            return {
                "qr_detected": False,
                "payload_raw": None,
                "extracted_keywords": [],
                "status": STATUS_CLEAN,
                "confidence_score": 0.0,
                "threat_indicators": [],
                "source_image": source_name,
                "crop_path": None,
                "error": "Failed to decode image matrix or file does not exist."
            }

        logger.info(f"Scanning target image: {source_name} [SHA-256: {source_hash[:12]}...]")

        # Run dual-layer QR detection & decoding
        decoded_items = self.detect_and_decode(img_mat, source_hash)

        if not decoded_items:
            logger.info(f"No QR codes detected in {source_name}.")
            scan_result = {
                "qr_detected": False,
                "payload_raw": None,
                "extracted_keywords": [],
                "status": STATUS_CLEAN,
                "confidence_score": 0.0,
                "threat_indicators": [],
                "source_image": source_name,
                "crop_path": None,
                "evidence_id": evidence_id,
            }
            self._save_to_intel_json(scan_result, source_hash, timestamp)
            return scan_result

        # Evaluate threat on primary decoded QR code
        primary_item = decoded_items[0]
        raw_payload = primary_item["payload"]
        threat_eval = self.evaluate_threat(raw_payload)

        # Aggregate threat indicators if multiple QR codes were found
        if len(decoded_items) > 1:
            for extra_item in decoded_items[1:]:
                extra_eval = self.evaluate_threat(extra_item["payload"])
                threat_eval["extracted_keywords"].extend(extra_eval["extracted_keywords"])
                threat_eval["threat_indicators"].extend(extra_eval["threat_indicators"])
                # Escalate status if any secondary code has higher severity
                if extra_eval["status"] == STATUS_DRUG_DETECTED:
                    threat_eval["status"] = STATUS_DRUG_DETECTED
                    threat_eval["confidence_score"] = max(threat_eval["confidence_score"], extra_eval["confidence_score"])
                elif extra_eval["status"] == STATUS_SUSPICIOUS and threat_eval["status"] == STATUS_CLEAN:
                    threat_eval["status"] = STATUS_SUSPICIOUS
                    threat_eval["confidence_score"] = max(threat_eval["confidence_score"], extra_eval["confidence_score"])

            threat_eval["extracted_keywords"] = sorted(list(set(threat_eval["extracted_keywords"])))
            threat_eval["threat_indicators"] = sorted(list(set(threat_eval["threat_indicators"])))

        scan_result = {
            "qr_detected": True,
            "payload_raw": raw_payload,
            "extracted_keywords": threat_eval["extracted_keywords"],
            "status": threat_eval["status"],
            "confidence_score": threat_eval["confidence_score"],
            "threat_indicators": threat_eval["threat_indicators"],
            "source_image": source_name,
            "crop_path": primary_item.get("crop_path"),
            "bbox": primary_item.get("bbox"),
            "engine_used": primary_item.get("engine"),
            "evidence_id": evidence_id,
            "all_decoded_codes": decoded_items,
        }

        logger.info(
            f"Scan Complete: QR Detected=True | Status={scan_result['status']} | "
            f"Conf={scan_result['confidence_score']} | Indicators={len(scan_result['threat_indicators'])}"
        )

        self._save_to_intel_json(scan_result, source_hash, timestamp)
        return scan_result

    def _save_to_intel_json(self, scan_result: Dict[str, Any], source_hash: str, timestamp: str) -> None:
        """Appends aggregate scan intelligence record to `data/qr_deep_intel.json`."""
        try:
            records = []
            if self.intel_output_path.is_file() and self.intel_output_path.stat().st_size > 0:
                try:
                    with open(self.intel_output_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, list):
                            records = loaded
                        elif isinstance(loaded, dict):
                            records = [loaded]
                except Exception as read_err:
                    logger.warning(f"Failed to read existing {self.intel_output_path.name}, writing clean: {read_err}")
                    records = []

            dossier_record = {
                "evidence_id": scan_result.get("evidence_id", generate_evidence_id()),
                "timestamp_utc": timestamp,
                "source_image": scan_result.get("source_image"),
                "source_sha256": source_hash,
                "qr_detected": scan_result.get("qr_detected", False),
                "payload_raw": scan_result.get("payload_raw"),
                "extracted_keywords": scan_result.get("extracted_keywords", []),
                "status": scan_result.get("status", STATUS_CLEAN),
                "confidence_score": scan_result.get("confidence_score", 0.0),
                "threat_indicators": scan_result.get("threat_indicators", []),
                "crop_path": scan_result.get("crop_path"),
                "engine_used": scan_result.get("engine_used"),
                "bbox": scan_result.get("bbox"),
            }

            records.append(dossier_record)

            with open(self.intel_output_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=4, ensure_ascii=False)

            logger.info(f"Persisted forensic evidence to {self.intel_output_path.resolve()} (Total Records: {len(records)})")
        except Exception as e:
            logger.error(f"Failed to persist dossier to {self.intel_output_path}: {e}")


# ==============================================================================
# PIPELINE HOOK & SINGLETON RUNNER FUNCTION
# ==============================================================================
_GLOBAL_DETECTOR: Optional[QRThreatDetector] = None


def get_qr_detector() -> QRThreatDetector:
    """Returns singleton instance of QRThreatDetector for efficient reuse."""
    global _GLOBAL_DETECTOR
    if _GLOBAL_DETECTOR is None:
        _GLOBAL_DETECTOR = QRThreatDetector()
    return _GLOBAL_DETECTOR


def scan_qr_payload(image_path: str) -> Dict[str, Any]:
    """
    Primary DrugShield AI Pipeline Hook:
    Scans an incoming image for QR codes, decodes payload data,
    evaluates threats against narcotics taxonomies and slangs,
    caches forensic crops, and saves intelligence output.

    Returns:
    {
        "qr_detected": True,
        "payload_raw": "...",
        "extracted_keywords": [...],
        "status": "DRUG_DETECTED" | "SUSPICIOUS" | "CLEAN",
        "confidence_score": float,
        "threat_indicators": [...]
    }
    """
    detector = get_qr_detector()
    return detector.scan(image_path)


# ==============================================================================
# CLI & DIAGNOSTIC RUNNER
# ==============================================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DrugShield AI - QR Threat Analysis Pipeline")
    parser.add_argument("--image", "-i", type=str, help="Path to image file to scan")
    parser.add_argument("--test", action="store_true", help="Run diagnostic test suite with synthetic QR payloads")
    args = parser.parse_args()

    if args.test:
        print("\n" + "=" * 65)
        print(" DRUGSHIELD AI - QR DETECTOR DIAGNOSTIC VERIFICATION ")
        print("=" * 65)

        detector = get_qr_detector()
        test_payloads = [
            ("Clean URL", "https://en.wikipedia.org/wiki/Pharmacology"),
            ("Explicit MDMA Menu", "MDMA 1g 3k menu DM @blr_supplies_bot"),
            ("Tramadol Pill Delivery", "Order Tramadol and Xanax pills stealth vacuum sealed"),
            ("Telegram Bot Redirect", "https://t.me/delhi_cartel_bot contact plug"),
            ("Obfuscated Slang", "Fresh chitta and ice score drop point"),
            ("Darknet Onion Mirror", "http://darkmarketxyz456abcdefg7890.onion/catalog"),
            ("Dead Drop Coordinates", "Drop pin: 28.6139, 77.2090 cash on drop"),
        ]

        for label, payload in test_payloads:
            res = detector.evaluate_threat(payload)
            print(f"\n[{label}] Payload: {payload}")
            print(f" -> Status: {res['status']} | Confidence: {res['confidence_score']}")
            print(f" -> Keywords: {res['extracted_keywords']}")
            print(f" -> Indicators: {res['threat_indicators']}")

    elif args.image:
        res = scan_qr_payload(args.image)
        print("\n" + json.dumps(res, indent=2))
    else:
        print("Use --image <path> or --test to run diagnostic tests.")
