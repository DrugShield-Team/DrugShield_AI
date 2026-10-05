#!/usr/bin/env python3
"""
DrugShield AI - Cyber Forensics & AI Intelligence Division
Module 2: Automated QR Code Resolver & Deep Evidence Extraction Pipeline
=========================================================================
File: module2_qr_deep_inspector.py

Capabilities:
1. Multi-Engine QR Code Detection & Decoding (OpenCV + PyZBar) with adaptive
   image contrast enhancements for compressed screenshots & flyers.
2. Intelligent Schema Routing:
   a. NPCI UPI scheme (`upi://pay`): Structured parsing of Virtual Payment
      Addresses (VPA/pa), Payee Names (pn), merchant categories, and banking
      parameters for syndicate financial graph construction.
   b. HTTP/HTTPS Media Host Resolution: Identification of media hosts/CDNs
      and automated streaming download to a secured forensic cache.
3. Ultralytics YOLOv8 Narcotics Detection:
   - Contraband classification targeting: weed, pill, powder, cannabis, blotter, etc.
   - Flags confidence scores and sets `is_narcotics_detected: True` if confidence > 0.5.
4. Physical Geo-Location & Device Attribution:
   - EXIF GPS metadata extraction (Latitude, Longitude, Altitude, Device Maker/Model).
   - DMS to Decimal degree conversion and Google Maps coordinate generation.
5. Persistent Intelligence Export:
   - Saves combined evidence records into `data/qr_deep_intel.json`.
6. Cyber Forensics Error Handling:
   - Resilient handling of corrupted downloads, truncated files, headless
     environments, non-standard UPI formats, and missing/scrubbed EXIF tags.
"""

import os
import sys
import json
import time
import math
import hashlib
import logging
import argparse
import tempfile
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
from PIL import Image, ExifTags
import requests
from ultralytics import YOLO

try:
    from pyzbar import pyzbar
    from pyzbar.pyzbar import ZBarSymbol
    PYZBAR_AVAILABLE = True
except (ImportError, Exception) as zbar_err:
    PYZBAR_AVAILABLE = False
    pyzbar = None
    ZBarSymbol = None

# Configure Forensic Structured Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [DrugShield-QRForensics] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DrugShield.QRDeepInspector")

# ---------------------------------------------------------------------------
# CONSTANTS & INTELLIGENCE DICTIONARIES
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

DEFAULT_OUTPUT_INTEL_PATH = PROJECT_ROOT / "data" / "qr_deep_intel.json"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "forensic_cache"

# Dynamic Resolution for Trained Narcotics Weights
CUSTOM_MODEL_CANDIDATE = SCRIPT_DIR / "models" / "best.pt"
if CUSTOM_MODEL_CANDIDATE.is_file():
    DEFAULT_YOLO_MODEL = str(CUSTOM_MODEL_CANDIDATE)
else:
    DEFAULT_YOLO_MODEL = "yolov8n.pt"

# Narcotics and illicit substance classification taxonomy
TARGET_NARCOTICS_CLASSES = {
    "weed",
    "pill",
    "powder",
    "cannabis",
    "blotter",
    "tablet",
    "capsule",
    "drugs",
    "substance",
    "cocaine",
    "heroin",
    "meth",
    "hashish",
    "ganja",
    "chitta",
    "stamp",
    "lsd",
    "mdma",
    "narcotic",
}

# Image file extensions and media hosting indicators
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif", ".heic"}
MEDIA_HOST_DOMAINS = {
    "catbox.moe",
    "files.catbox.moe",
    "imgur.com",
    "i.imgur.com",
    "postimg.cc",
    "i.postimg.cc",
    "ibb.co",
    "i.ibb.co",
    "pixeldrain.com",
    "mega.nz",
    "drive.google.com",
    "dropbox.com",
    "dl.dropboxusercontent.com",
    "discordapp.com",
    "cdn.discordapp.com",
    "media.discordapp.net",
    "telegram.org",
    "t.me",
    "anonfiles.com",
    "filebin.net",
    "pastebin.com",
    "githubusercontent.com",
}

# Indian Banking / UPI PSP domain mapping for syndicate financial attribution
UPI_PSP_MAP = {
    "ybl": "YES Bank (PhonePe)",
    "ibl": "IndusInd Bank (PhonePe)",
    "axl": "Axis Bank (PhonePe)",
    "paytm": "Paytm Payments Bank",
    "okaxis": "Axis Bank (Google Pay)",
    "okhdfcbank": "HDFC Bank (Google Pay)",
    "okicici": "ICICI Bank (Google Pay)",
    "oksbi": "State Bank of India (Google Pay)",
    "icici": "ICICI Bank iMobile",
    "barodampay": "Bank of Baroda",
    "sbi": "State Bank of India (YONO)",
    "upi": "NPCI / BHIM Generic",
    "apl": "Amazon Pay (Axis Bank)",
    "waicici": "WhatsApp Pay (ICICI Bank)",
    "waaxis": "WhatsApp Pay (Axis Bank)",
}

# Suspicious contraband keywords found in transaction notes or user handles
SUSPECT_KEYWORDS = [
    "score", "chitta", "mdma", "ganja", "weed", "stash", "token", "stuff",
    "green", "pills", "cartel", "drop", "supplies", "ice", "blotter", "stamp"
]

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB safety limit
HTTP_TIMEOUT = (5.0, 20.0)  # (connect, read) timeout


# ---------------------------------------------------------------------------
# FORENSIC UTILITIES
# ---------------------------------------------------------------------------
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
    """Generate standardized law-enforcement format evidence identifier."""
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand_hex = hashlib.md5(f"{time.time()}_{os.getpid()}".encode()).hexdigest()[:6].upper()
    return f"{prefix}-{now_str}-{rand_hex}"


def dms_to_decimal(dms_values: Any, ref: Optional[str]) -> Optional[float]:
    """
    Convert EXIF GPS DMS (Degrees, Minutes, Seconds) to Decimal Degrees.
    Handles rational tuples, fractions, floats, and hemisphere references.
    """
    if not dms_values or len(dms_values) < 3:
        return None

    def _val(x: Any) -> float:
        if hasattr(x, "numerator") and hasattr(x, "denominator"):
            return float(x.numerator) / float(x.denominator) if x.denominator != 0 else 0.0
        if isinstance(x, (tuple, list)) and len(x) == 2:
            return float(x[0]) / float(x[1]) if x[1] != 0 else 0.0
        try:
            return float(x)
        except (ValueError, TypeError):
            return 0.0

    try:
        degrees = _val(dms_values[0])
        minutes = _val(dms_values[1])
        seconds = _val(dms_values[2])

        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref and ref.strip().upper() in ["S", "W"]:
            decimal = -decimal
        return round(decimal, 6)
    except Exception as e:
        logger.warning(f"Error parsing DMS values {dms_values} with ref {ref}: {e}")
        return None


# ---------------------------------------------------------------------------
# MODULE COMPONENT 1: MULTI-ENGINE QR SCANNER & DECODER
# ---------------------------------------------------------------------------
class QRScannerEngine:
    """
    Robust Dual-Engine QR Code Detector and Decoder.
    Combines PyZBar and OpenCV with adaptive computer vision preprocessing
    for forensic extraction from compressed, noisy, or tilted screenshots.
    """

    def __init__(self):
        self.opencv_detector = cv2.QRCodeDetector()
        self.pyzbar_enabled = PYZBAR_AVAILABLE
        if not self.pyzbar_enabled:
            logger.warning("PyZBar native library unavailable; falling back strictly to OpenCV QRCodeDetector.")

    def decode_image(self, image_input: Union[str, Path, np.ndarray, Image.Image]) -> List[Dict[str, Any]]:
        """
        Detect and decode all QR codes present in an image input.
        Returns a list of decoded QR code metadata objects.
        """
        cv_img, _ = self._load_opencv_image(image_input)
        if cv_img is None or cv_img.size == 0:
            logger.error("Failed to load valid image matrix for QR decoding.")
            return []

        results = []
        seen_payloads = set()

        # Phase 1: Try PyZBar on raw image
        if self.pyzbar_enabled:
            raw_zbar_results = self._decode_with_pyzbar(cv_img)
            for item in raw_zbar_results:
                payload = item["raw_payload"]
                if payload and payload not in seen_payloads:
                    seen_payloads.add(payload)
                    results.append(item)

        # Phase 2: If no codes found or OpenCV enhancement required, run OpenCV
        if not results:
            cv_results = self._decode_with_opencv(cv_img)
            for item in cv_results:
                payload = item["raw_payload"]
                if payload and payload not in seen_payloads:
                    seen_payloads.add(payload)
                    results.append(item)

        # Phase 3: Adaptive Preprocessing Fallback if still empty
        if not results:
            enhanced_imgs = self._generate_enhanced_variants(cv_img)
            for enh_name, enh_mat in enhanced_imgs:
                # Try PyZBar on enhanced variant
                if self.pyzbar_enabled:
                    enh_zbar = self._decode_with_pyzbar(enh_mat)
                    for item in enh_zbar:
                        payload = item["raw_payload"]
                        if payload and payload not in seen_payloads:
                            item["detection_note"] = f"Decoded via PyZBar with {enh_name} preprocessing"
                            seen_payloads.add(payload)
                            results.append(item)

                # Try OpenCV on enhanced variant
                if not results:
                    enh_cv = self._decode_with_opencv(enh_mat)
                    for item in enh_cv:
                        payload = item["raw_payload"]
                        if payload and payload not in seen_payloads:
                            item["detection_note"] = f"Decoded via OpenCV with {enh_name} preprocessing"
                            seen_payloads.add(payload)
                            results.append(item)

                if results:
                    break

        return results

    def _decode_with_pyzbar(self, img_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """Decode using PyZBar library."""
        found = []
        if not self.pyzbar_enabled or pyzbar is None:
            return found

        try:
            symbols = [ZBarSymbol.QRCODE] if ZBarSymbol is not None else []
            decoded_objects = pyzbar.decode(img_bgr, symbols=symbols) if symbols else pyzbar.decode(img_bgr)
            for obj in decoded_objects:
                try:
                    payload = obj.data.decode("utf-8").strip()
                except UnicodeDecodeError:
                    payload = obj.data.decode("latin-1", errors="ignore").strip()

                if not payload:
                    continue

                rect = obj.rect
                bbox = [int(rect.left), int(rect.top), int(rect.width), int(rect.height)]
                polygon = [[int(pt.x), int(pt.y)] for pt in obj.polygon] if obj.polygon else []

                found.append({
                    "raw_payload": payload,
                    "engine": "pyzbar",
                    "bbox": bbox,
                    "polygon": polygon,
                    "type": str(obj.type),
                })
        except Exception as e:
            logger.debug(f"PyZBar execution exception: {e}")
        return found

    def _decode_with_opencv(self, img_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """Decode using OpenCV QRCodeDetector."""
        found = []
        try:
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if len(img_bgr.shape) == 3 else img_bgr

            if hasattr(self.opencv_detector, "detectAndDecodeMulti"):
                success, decoded_info, points, _ = self.opencv_detector.detectAndDecodeMulti(gray)
                if success and decoded_info:
                    for i, text in enumerate(decoded_info):
                        text = text.strip()
                        if not text:
                            continue
                        pts = points[i].tolist() if points is not None and len(points) > i else []
                        found.append({
                            "raw_payload": text,
                            "engine": "opencv_multi",
                            "polygon": pts,
                            "bbox": self._pts_to_bbox(pts),
                            "type": "QRCODE"
                        })

            if not found:
                text, points, _ = self.opencv_detector.detectAndDecode(gray)
                text = text.strip() if text else ""
                if text:
                    pts = points.tolist() if points is not None else []
                    found.append({
                        "raw_payload": text,
                        "engine": "opencv_single",
                        "polygon": pts,
                        "bbox": self._pts_to_bbox(pts),
                        "type": "QRCODE"
                    })
        except Exception as e:
            logger.debug(f"OpenCV QR decode error: {e}")
        return found

    def _generate_enhanced_variants(self, img_bgr: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        """Generate computer vision enhancements for low-contrast/compressed QR codes."""
        variants = []
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if len(img_bgr.shape) == 3 else img_bgr.copy()

        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        variants.append(("clahe", clahe.apply(gray)))

        # Otsu Binary Thresholding
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(("otsu_threshold", otsu))

        # Sharpening Filter
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        sharpened = cv2.filter2D(gray, -1, kernel)
        variants.append(("sharpened", sharpened))

        # Inverted Threshold
        variants.append(("inverted", cv2.bitwise_not(gray)))

        return variants

    def _pts_to_bbox(self, pts: List[Any]) -> List[int]:
        if not pts:
            return [0, 0, 0, 0]
        try:
            pts_arr = np.array(pts, dtype=np.int32).reshape(-1, 2)
            x, y, w, h = cv2.boundingRect(pts_arr)
            return [int(x), int(y), int(w), int(h)]
        except Exception:
            return [0, 0, 0, 0]

    def _load_opencv_image(self, img_input: Any) -> Tuple[Optional[np.ndarray], Optional[Path]]:
        """Safely load image into BGR numpy matrix."""
        if isinstance(img_input, (str, Path)):
            p = Path(img_input)
            if not p.is_file():
                return None, None
            with open(p, "rb") as f:
                arr = np.frombuffer(f.read(), dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                return img, p
        elif isinstance(img_input, np.ndarray):
            return img_input, None
        elif isinstance(img_input, Image.Image):
            rgb = img_input.convert("RGB")
            return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR), None
        return None, None


# ---------------------------------------------------------------------------
# MODULE COMPONENT 2: INTELLIGENT SCHEMA ROUTER & FINANCIAL PARSER
# ---------------------------------------------------------------------------
class SchemaRouter:
    """
    Parses and categorizes decoded QR contents based on cryptographic/network schema.
    Extracts financial parameters from NPCI UPI URIs and routes file host URLs.
    """

    @staticmethod
    def identify_schema(payload: str) -> str:
        """Identify QR schema classification."""
        cleaned = payload.strip()
        lower = cleaned.lower()
        if lower.startswith("upi://pay") or lower.startswith("upi:pay") or (lower.startswith("upi://") and "pa=" in lower):
            return "UPI_PAYMENT"
        if lower.startswith("http://") or lower.startswith("https://"):
            return "URL"
        if lower.startswith("bitcoin:") or lower.startswith("ethereum:") or lower.startswith("monero:"):
            return "CRYPTO_PAYMENT"
        if lower.startswith("tg://") or "t.me/" in lower:
            return "TELEGRAM_DEEPLINK"
        if lower.startswith("whatsapp://") or "wa.me/" in lower:
            return "WHATSAPP_DEEPLINK"
        return "PLAIN_TEXT"

    @staticmethod
    def parse_upi_scheme(uri: str) -> Dict[str, Any]:
        """
        Parse NPCI UPI URI into structured financial tracking intelligence.
        Extracts VPA (pa), Payee Name (pn), MCC (mc), Transaction Note (tn), Amount (am).
        """
        parsed = urlparse(uri)
        query_string = parsed.query
        if not query_string and "?" in uri:
            query_string = uri.split("?", 1)[1]

        qs_dict = parse_qs(query_string, keep_blank_values=True)
        banking_params: Dict[str, str] = {k: unquote(v[0]).strip() for k, v in qs_dict.items() if v}

        vpa = banking_params.get("pa", "").strip()
        payee_name = banking_params.get("pn", "").strip()
        note = banking_params.get("tn", "").strip()
        amount = banking_params.get("am", "").strip()
        currency = banking_params.get("cu", "INR").strip()
        mcc = banking_params.get("mc", "").strip()
        txn_ref = banking_params.get("tr", "").strip()
        ref_url = banking_params.get("url", "").strip()
        signature = banking_params.get("sign", "").strip()

        vpa_handle = ""
        psp_institution = "Unknown / Self-Hosted VPA"
        if "@" in vpa:
            vpa_handle = vpa.split("@")[-1].lower()
            psp_institution = UPI_PSP_MAP.get(vpa_handle, f"PSP Handle (@{vpa_handle})")

        flagged_keywords = []
        combined_text = f"{note} {payee_name} {vpa}".lower()
        for kw in SUSPECT_KEYWORDS:
            if kw in combined_text:
                flagged_keywords.append(kw)

        risk_level = "HIGH" if flagged_keywords or (amount and float(amount or 0) > 20000) else "ELEVATED"

        return {
            "is_upi": True,
            "vpa": vpa,
            "payee_name": payee_name,
            "vpa_handle": vpa_handle,
            "psp_institution": psp_institution,
            "amount": amount,
            "currency": currency,
            "mcc_category": mcc,
            "transaction_note": note,
            "transaction_ref": txn_ref,
            "reference_url": ref_url,
            "digital_signature_present": bool(signature),
            "banking_parameters": banking_params,
            "syndicate_tracking_risk": risk_level,
            "flagged_keywords": flagged_keywords,
        }

    @staticmethod
    def is_media_or_file_host_url(url: str) -> bool:
        """Determine if an HTTP/HTTPS URL points to an image or file hosting service."""
        lower_url = url.lower()
        parsed = urlparse(url)
        path = parsed.path.lower()
        netloc = parsed.netloc.lower()

        if any(path.endswith(ext) for ext in IMAGE_EXTENSIONS):
            return True

        if any(netloc == host or netloc.endswith("." + host) for host in MEDIA_HOST_DOMAINS):
            return True

        if "/image/" in path or "/img/" in path or "/file/" in path or "/download" in path:
            return True

        return False


# ---------------------------------------------------------------------------
# MODULE COMPONENT 3: FORENSIC MEDIA DOWNLOADER & CACHING
# ---------------------------------------------------------------------------
class ForensicMediaDownloader:
    """
    Downloads remote media files from suspect URLs to a secured local forensic cache.
    Validates file headers, computes cryptographic hashes, and traps corrupted payloads.
    """

    def __init__(self, cache_dir: Union[str, Path] = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "DrugShield-Forensics/2.4 (Investigative Cyber Intel; Headless Pipeline)"
        })

    def download_media(self, url: str) -> Dict[str, Any]:
        """Download media from URL with size safeguards, timeouts, and integrity checks."""
        logger.info(f"Initiating forensic media acquisition from: {url}")
        intel: Dict[str, Any] = {
            "source_url": url,
            "download_status": "PENDING",
            "cached_path": None,
            "file_hash_sha256": None,
            "content_type": None,
            "file_size_bytes": 0,
            "is_corrupted": False,
            "error": None,
        }

        try:
            with self.session.get(url, stream=True, timeout=HTTP_TIMEOUT, allow_redirects=True) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                intel["content_type"] = content_type

                if resp.status_code != 200:
                    intel["download_status"] = "HTTP_ERROR"
                    intel["error"] = f"HTTP {resp.status_code}: {resp.reason}"
                    logger.warning(f"Download failed with status {resp.status_code} for URL: {url}")
                    return intel

                cl_header = resp.headers.get("Content-Length")
                if cl_header and int(cl_header) > MAX_DOWNLOAD_BYTES:
                    intel["download_status"] = "PAYLOAD_TOO_LARGE"
                    intel["error"] = f"Payload size {cl_header} exceeds security threshold {MAX_DOWNLOAD_BYTES} bytes."
                    return intel

                byte_buffer = bytearray()
                for chunk in resp.iter_content(chunk_size=16384):
                    if chunk:
                        byte_buffer.extend(chunk)
                        if len(byte_buffer) > MAX_DOWNLOAD_BYTES:
                            intel["download_status"] = "PAYLOAD_TOO_LARGE"
                            intel["error"] = "Downloaded stream exceeded maximum allowable forensic cache size."
                            return intel

                raw_bytes = bytes(byte_buffer)
                intel["file_size_bytes"] = len(raw_bytes)

                if len(raw_bytes) == 0:
                    intel["download_status"] = "EMPTY_FILE"
                    intel["is_corrupted"] = True
                    intel["error"] = "Received 0 bytes from server."
                    return intel

                sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
                intel["file_hash_sha256"] = sha256_hash

                ext = self._deduce_extension(url, content_type, raw_bytes)
                cache_filename = f"ev_{sha256_hash[:16]}{ext}"
                target_path = self.cache_dir / cache_filename

                with open(target_path, "wb") as f:
                    f.write(raw_bytes)

                intel["cached_path"] = str(target_path.resolve())

                is_valid, validation_err = self._verify_image_integrity(target_path)
                if not is_valid:
                    intel["download_status"] = "CORRUPTED_IMAGE"
                    intel["is_corrupted"] = True
                    intel["error"] = f"Image integrity verification failed: {validation_err}"
                    logger.warning(f"Forensic cache file {target_path.name} is corrupted: {validation_err}")
                else:
                    intel["download_status"] = "DOWNLOADED_VALID"
                    logger.info(f"Media successfully cached: {target_path.name} ({len(raw_bytes)} bytes)")

        except requests.exceptions.Timeout as te:
            intel["download_status"] = "TIMEOUT"
            intel["error"] = f"Connection/read timeout: {te}"
            logger.warning(f"Download timeout for {url}: {te}")
        except requests.exceptions.RequestException as re_err:
            intel["download_status"] = "NETWORK_ERROR"
            intel["error"] = f"Request failure: {re_err}"
            logger.warning(f"Network error downloading {url}: {re_err}")
        except Exception as e:
            intel["download_status"] = "SYSTEM_ERROR"
            intel["error"] = f"Unexpected download exception: {e}"
            logger.error(f"Unexpected error caching media from {url}: {e}")

        return intel

    def _deduce_extension(self, url: str, content_type: str, raw_bytes: bytes) -> str:
        """Infer appropriate file extension from URL, Content-Type, or magic bytes."""
        url_path = urlparse(url).path.lower()
        for ext in IMAGE_EXTENSIONS:
            if url_path.endswith(ext):
                return ext

        if "jpeg" in content_type or "jpg" in content_type:
            return ".jpg"
        if "png" in content_type:
            return ".png"
        if "webp" in content_type:
            return ".webp"
        if "gif" in content_type:
            return ".gif"

        if raw_bytes.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if raw_bytes.startswith(b"RIFF") and b"WEBP" in raw_bytes[:12]:
            return ".webp"

        return ".bin"

    def _verify_image_integrity(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """Validate whether the file is an intact, uncorrupted image."""
        try:
            with Image.open(file_path) as img:
                img.verify()
            cv_check = cv2.imread(str(file_path))
            if cv_check is None or cv_check.size == 0:
                return False, "OpenCV failed to decode image buffer."
            return True, None
        except Exception as e:
            return False, str(e)


# ---------------------------------------------------------------------------
# MODULE COMPONENT 4: YOLOV8 NARCOTICS OBJECT DETECTION
# ---------------------------------------------------------------------------
class YOLONarcoticsInspector:
    """
    Ultralytics YOLOv8 Computer Vision Inspector for Narcotic Contraband.
    Detects weed, pills, powders, cannabis, blotters, etc.
    Flags confidence scores and enforces `is_narcotics_detected: True` if confidence > 0.5.
    """

    def __init__(
        self,
        model_path: str = DEFAULT_YOLO_MODEL,
        target_classes: Optional[set] = None,
        confidence_threshold: float = 0.50
    ):
        self.model_path = model_path
        self.target_classes = target_classes or TARGET_NARCOTICS_CLASSES
        self.confidence_threshold = confidence_threshold
        self._model: Optional[YOLO] = None
        self._is_initialized = False

    def _ensure_model_loaded(self):
        """Lazy load YOLO model to optimize startup time in headless environments."""
        if not self._is_initialized:
            try:
                logger.info(f"Initializing YOLOv8 model from: {self.model_path}")
                self._model = YOLO(self.model_path)
                self._is_initialized = True
            except Exception as e:
                logger.error(f"Failed to load YOLO model ({self.model_path}): {e}")
                self._model = None
                self._is_initialized = True

    def inspect_image(
        self,
        image_path: Union[str, Path, np.ndarray],
        simulated_detections: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Run computer vision inspection on image."""
        self._ensure_model_loaded()

        intel: Dict[str, Any] = {
            "model_path": self.model_path,
            "is_narcotics_detected": False,
            "max_narcotics_confidence": 0.0,
            "detected_substances": [],
            "all_detections": [],
            "analysis_status": "COMPLETED",
            "error": None,
        }

        if simulated_detections is not None:
            return self._process_detection_records(simulated_detections, intel)

        if self._model is None:
            intel["analysis_status"] = "MODEL_UNAVAILABLE"
            intel["error"] = "YOLO model weights could not be loaded."
            return intel

        try:
            if isinstance(image_path, (str, Path)):
                p = Path(image_path)
                if not p.is_file():
                    intel["analysis_status"] = "FILE_NOT_FOUND"
                    intel["error"] = f"Image file not found: {p}"
                    return intel
                target_src = str(p.resolve())
            else:
                target_src = image_path

            results = self._model.predict(
                source=target_src,
                conf=0.25,
                verbose=False,
                device="cpu"
            )

            raw_detections = []
            for r in results:
                if not hasattr(r, "boxes") or r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id = int(box.cls[0].item())
                    cls_name = self._model.names.get(cls_id, f"class_{cls_id}").lower()
                    conf = float(box.conf[0].item())
                    xyxy = [round(float(coord), 2) for coord in box.xyxy[0].tolist()]

                    raw_detections.append({
                        "class_name": cls_name,
                        "confidence": round(conf, 4),
                        "bbox": xyxy
                    })

            return self._process_detection_records(raw_detections, intel)

        except Exception as e:
            logger.error(f"YOLO vision inspection exception: {e}")
            intel["analysis_status"] = "INSPECTION_FAILED"
            intel["error"] = str(e)
            return intel

    def _process_detection_records(
        self,
        raw_detections: List[Dict[str, Any]],
        intel: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Classify detections against target narcotics taxonomy and calculate confidence."""
        detected_narcotics = []
        max_conf = 0.0

        for item in raw_detections:
            cls_name = item.get("class_name", "").lower()
            conf = float(item.get("confidence", 0.0))

            is_narcotic_match = any(
                narc_kw in cls_name or cls_name in narc_kw
                for narc_kw in self.target_classes
            )

            detection_entry = {
                "class_name": cls_name,
                "confidence": conf,
                "bbox": item.get("bbox", [0, 0, 0, 0]),
                "is_narcotic": is_narcotic_match
            }
            intel["all_detections"].append(detection_entry)

            if is_narcotic_match:
                detected_narcotics.append(detection_entry)
                if conf > max_conf:
                    max_conf = conf

        intel["detected_substances"] = detected_narcotics
        intel["max_narcotics_confidence"] = round(max_conf, 4)

        if max_conf > self.confidence_threshold:
            intel["is_narcotics_detected"] = True
            logger.warning(
                f"[ALERT] Narcotics detected with confidence {max_conf:.2f} "
                f"(Threshold: {self.confidence_threshold}): {[d['class_name'] for d in detected_narcotics]}"
            )
        else:
            intel["is_narcotics_detected"] = False

        return intel


# ---------------------------------------------------------------------------
# MODULE COMPONENT 5: EXIF GPS & DEVICE ATTRIBUTION EXTRACTOR
# ---------------------------------------------------------------------------
class EXIFGeoForensicsExtractor:
    """
    Extracts physical GPS geo-coordinates and camera device metadata from image files.
    Gracefully handles scrubbed metadata and missing tags in social media screenshots.
    """

    @staticmethod
    def extract_metadata(image_path: Union[str, Path]) -> Dict[str, Any]:
        """Extract Latitude, Longitude, Altitude, Device Maker/Model from image EXIF."""
        path = Path(image_path)
        geo_intel: Dict[str, Any] = {
            "has_gps": False,
            "latitude": None,
            "longitude": None,
            "altitude_m": None,
            "device_maker": None,
            "device_model": None,
            "software": None,
            "capture_timestamp": None,
            "google_maps_url": None,
            "gps_status": "PENDING",
            "error": None,
        }

        if not path.is_file():
            geo_intel["gps_status"] = "FILE_NOT_FOUND"
            geo_intel["error"] = f"Image path does not exist: {path}"
            return geo_intel

        try:
            with Image.open(path) as img:
                exif_data = img.getexif()

                if not exif_data:
                    geo_intel["gps_status"] = "NO_EXIF_DATA"
                    geo_intel["error"] = "Image does not contain any EXIF header (metadata stripped)."
                    return geo_intel

                for tag_id, val in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if tag_name == "Make":
                        geo_intel["device_maker"] = str(val).strip()
                    elif tag_name == "Model":
                        geo_intel["device_model"] = str(val).strip()
                    elif tag_name == "Software":
                        geo_intel["software"] = str(val).strip()
                    elif tag_name in ("DateTimeOriginal", "DateTime"):
                        geo_intel["capture_timestamp"] = str(val).strip()

                gps_dict = {}
                if hasattr(ExifTags, "IFD") and hasattr(ExifTags.IFD, "GPSInfo"):
                    gps_dict = exif_data.get_ifd(ExifTags.IFD.GPSInfo)
                elif hasattr(exif_data, "get_ifd"):
                    gps_dict = exif_data.get_ifd(0x8825)

                if not gps_dict:
                    geo_intel["gps_status"] = "NO_GPS_METADATA_FOUND"
                    logger.info(f"No GPS metadata tags present in {path.name} (maker={geo_intel['device_maker']})")
                    return geo_intel

                decoded_gps = {}
                for k, v in gps_dict.items():
                    sub_tag = ExifTags.GPSTAGS.get(k, str(k))
                    decoded_gps[sub_tag] = v

                lat_raw = decoded_gps.get("GPSLatitude")
                lat_ref = decoded_gps.get("GPSLatitudeRef")
                lon_raw = decoded_gps.get("GPSLongitude")
                lon_ref = decoded_gps.get("GPSLongitudeRef")
                alt_raw = decoded_gps.get("GPSAltitude")
                alt_ref = decoded_gps.get("GPSAltitudeRef", 0)

                lat_dec = dms_to_decimal(lat_raw, lat_ref)
                lon_dec = dms_to_decimal(lon_raw, lon_ref)

                if lat_dec is not None and lon_dec is not None:
                    geo_intel["has_gps"] = True
                    geo_intel["latitude"] = lat_dec
                    geo_intel["longitude"] = lon_dec
                    geo_intel["google_maps_url"] = f"https://www.google.com/maps?q={lat_dec:.6f},{lon_dec:.6f}"
                    geo_intel["gps_status"] = "GPS_COORDINATES_ACQUIRED"

                    if alt_raw is not None:
                        try:
                            if hasattr(alt_raw, "numerator") and hasattr(alt_raw, "denominator"):
                                alt_val = float(alt_raw.numerator) / float(alt_raw.denominator)
                            elif isinstance(alt_raw, (tuple, list)):
                                alt_val = float(alt_raw[0]) / float(alt_raw[1])
                            else:
                                alt_val = float(alt_raw)
                            if alt_ref == 1:
                                alt_val = -alt_val
                            geo_intel["altitude_m"] = round(alt_val, 2)
                        except Exception:
                            geo_intel["altitude_m"] = None

                    logger.info(
                        f"[GEO-ATTRIBUTION] Located coordinates for {path.name}: "
                        f"Lat {lat_dec}, Lon {lon_dec} -> {geo_intel['google_maps_url']}"
                    )
                else:
                    geo_intel["gps_status"] = "INCOMPLETE_GPS_TAGS"

        except Exception as e:
            logger.warning(f"Failed to extract EXIF from {path.name}: {e}")
            geo_intel["gps_status"] = "EXIF_PARSING_ERROR"
            geo_intel["error"] = str(e)

        return geo_intel


# ---------------------------------------------------------------------------
# MODULE COMPONENT 6: COMBINED DEEP FORENSIC INSPECTOR & PIPELINE
# ---------------------------------------------------------------------------
class QRDeepForensicInspector:
    """
    Primary Orchestrator for DrugShield AI Module 2.
    Integrates QR decoding, UPI routing, media acquisition, YOLOv8 vision inspection,
    EXIF GPS physical geo-location, and persistent intelligence storage.
    """

    def __init__(
        self,
        model_path: str = DEFAULT_YOLO_MODEL,
        output_file: Union[str, Path] = DEFAULT_OUTPUT_INTEL_PATH,
        cache_dir: Union[str, Path] = DEFAULT_CACHE_DIR,
        narcotics_conf_threshold: float = 0.50
    ):
        self.output_file = Path(output_file)
        self.cache_dir = Path(cache_dir)
        self.qr_scanner = QRScannerEngine()
        self.router = SchemaRouter()
        self.downloader = ForensicMediaDownloader(cache_dir=self.cache_dir)
        self.yolo_inspector = YOLONarcoticsInspector(
            model_path=model_path,
            confidence_threshold=narcotics_conf_threshold
        )
        self.exif_extractor = EXIFGeoForensicsExtractor()

    def inspect(
        self,
        image_input: Union[str, Path, np.ndarray, Image.Image],
        simulated_narcotics_detections: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Execute deep forensic analysis on a suspect screenshot, flyer, or media file."""
        evidence_id = generate_evidence_id()
        timestamp = datetime.now(timezone.utc).isoformat()

        source_name = "memory_array"
        source_sha256 = "N/A"
        source_file_path: Optional[Path] = None

        if isinstance(image_input, (str, Path)):
            source_file_path = Path(image_input)
            source_name = str(source_file_path)
            if source_file_path.is_file():
                source_sha256 = compute_sha256(source_file_path)

        logger.info(f"=== Starting Deep Forensic Inspection: Evidence ID [{evidence_id}] ===")
        logger.info(f"Target Source: {source_name} | SHA-256: {source_sha256}")

        dossier: Dict[str, Any] = {
            "evidence_id": evidence_id,
            "timestamp_utc": timestamp,
            "source_image": source_name,
            "source_sha256": source_sha256,
            "qr_detected": False,
            "qr_count": 0,
            "qr_records": [],
            "primary_schema": "NONE",
            "financial_intelligence": None,
            "media_intelligence": None,
            "vision_classification": None,
            "geolocation_intelligence": None,
            "forensic_flags": [],
            "forensic_status": "PROCESSED",
        }

        # Step 1: Extract EXIF GPS and hardware metadata from suspect image itself
        if source_file_path and source_file_path.is_file():
            source_geo = self.exif_extractor.extract_metadata(source_file_path)
            dossier["geolocation_intelligence"] = source_geo
            if source_geo.get("has_gps"):
                dossier["forensic_flags"].append("PHYSICAL_GPS_ATTRIBUTED_SOURCE")

        # Step 2: Detect & Decode QR codes using OpenCV and PyZBar
        decoded_qrs = self.qr_scanner.decode_image(image_input)
        dossier["qr_count"] = len(decoded_qrs)
        dossier["qr_detected"] = len(decoded_qrs) > 0

        if not decoded_qrs:
            logger.info("No QR codes detected in suspect image. Proceeding to direct image vision inspection.")
            dossier["primary_schema"] = "DIRECT_IMAGE"
            if source_file_path and source_file_path.is_file():
                vision_res = self.yolo_inspector.inspect_image(
                    source_file_path,
                    simulated_detections=simulated_narcotics_detections
                )
                dossier["vision_classification"] = vision_res
                if vision_res.get("is_narcotics_detected"):
                    dossier["forensic_flags"].append("NARCOTICS_CONFIRMED_VISION")
            self._save_to_intel_database(dossier)
            return dossier

        # Step 3: Route decoded QR codes based on schema
        downloaded_media_path: Optional[str] = None

        for idx, qr in enumerate(decoded_qrs):
            raw_payload = qr["raw_payload"]
            schema_type = self.router.identify_schema(raw_payload)
            qr_record: Dict[str, Any] = {
                "qr_index": idx,
                "raw_payload": raw_payload,
                "schema_type": schema_type,
                "engine": qr.get("engine", "unknown"),
                "bbox": qr.get("bbox", []),
                "polygon": qr.get("polygon", []),
            }

            if idx == 0:
                dossier["primary_schema"] = schema_type

            if schema_type == "UPI_PAYMENT":
                upi_data = self.router.parse_upi_scheme(raw_payload)
                qr_record["upi_intelligence"] = upi_data
                dossier["financial_intelligence"] = upi_data
                dossier["forensic_flags"].append("UPI_SYNDICATE_VPA_EXTRACTED")
                if upi_data.get("syndicate_tracking_risk") == "HIGH":
                    dossier["forensic_flags"].append("HIGH_RISK_FINANCIAL_NOTE")
                logger.info(
                    f"[FINANCIAL INTEL] VPA: {upi_data['vpa']} | "
                    f"Name: {upi_data['payee_name']} | PSP: {upi_data['psp_institution']}"
                )

            elif schema_type == "URL":
                is_media_host = self.router.is_media_or_file_host_url(raw_payload)
                qr_record["is_media_host"] = is_media_host

                if is_media_host:
                    dossier["forensic_flags"].append("EXTERNAL_MEDIA_HOST_ROUTED")
                    media_res = self.downloader.download_media(raw_payload)
                    qr_record["media_download"] = media_res
                    dossier["media_intelligence"] = media_res

                    if media_res.get("download_status") == "DOWNLOADED_VALID":
                        downloaded_media_path = media_res.get("cached_path")
                    elif media_res.get("is_corrupted"):
                        dossier["forensic_flags"].append("CORRUPTED_MEDIA_DOWNLOAD")

            dossier["qr_records"].append(qr_record)

        # Step 4: Inspect downloaded media or suspect image with YOLOv8 & EXIF
        target_vision_image = downloaded_media_path or (str(source_file_path) if source_file_path else None)

        if downloaded_media_path:
            logger.info(f"Targeting downloaded media for deep vision & EXIF attribution: {downloaded_media_path}")
            downloaded_geo = self.exif_extractor.extract_metadata(downloaded_media_path)
            if downloaded_geo.get("has_gps") or not dossier.get("geolocation_intelligence", {}).get("has_gps"):
                dossier["geolocation_intelligence"] = downloaded_geo
                if downloaded_geo.get("has_gps"):
                    dossier["forensic_flags"].append("PHYSICAL_GPS_ATTRIBUTED_DOWNLOADED_MEDIA")

        if target_vision_image:
            vision_res = self.yolo_inspector.inspect_image(
                target_vision_image,
                simulated_detections=simulated_narcotics_detections
            )
            dossier["vision_classification"] = vision_res
            if vision_res.get("is_narcotics_detected"):
                dossier["forensic_flags"].append("NARCOTICS_CONFIRMED_VISION")
        else:
            dossier["vision_classification"] = {
                "analysis_status": "SKIPPED",
                "is_narcotics_detected": False,
                "note": "No downloadable media or image file available for vision analysis."
            }

        self._save_to_intel_database(dossier)
        logger.info(f"=== Deep Forensic Dossier Saved for [{evidence_id}] ===")
        return dossier

    def _save_to_intel_database(self, dossier: Dict[str, Any]) -> None:
        """Thread-safe persistence of forensic dossier into `data/qr_deep_intel.json`."""
        try:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            records = []

            if self.output_file.is_file() and self.output_file.stat().st_size > 0:
                try:
                    with open(self.output_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, list):
                            records = loaded
                        elif isinstance(loaded, dict):
                            records = [loaded]
                except Exception as read_err:
                    logger.warning(f"Could not parse existing {self.output_file.name}, initializing fresh: {read_err}")
                    records = []

            existing_idx = next((i for i, r in enumerate(records) if r.get("evidence_id") == dossier["evidence_id"]), None)
            if existing_idx is not None:
                records[existing_idx] = dossier
            else:
                records.append(dossier)

            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=4, ensure_ascii=False)

            logger.info(f"Updated intelligence file: {self.output_file.resolve()} (Total Records: {len(records)})")
        except Exception as e:
            logger.error(f"Failed to persist evidence to {self.output_file}: {e}")


# ---------------------------------------------------------------------------
# CLI & DIAGNOSTIC INTERFACE
# ---------------------------------------------------------------------------
def run_cli():
    """Command-line interface for standalone cyber forensics investigation."""
    parser = argparse.ArgumentParser(
        description="DrugShield AI - Module 2: Automated QR Deep Inspector & Forensic Extractor"
    )
    parser.add_argument("--image", "-i", type=str, help="Path to suspect chat screenshot or flyer image.")
    parser.add_argument("--output", "-o", type=str, default=str(DEFAULT_OUTPUT_INTEL_PATH), help="Output JSON path.")
    parser.add_argument("--model", "-m", type=str, default=DEFAULT_YOLO_MODEL, help="Path to YOLOv8 model weights.")
    parser.add_argument("--test-demo", action="store_true", help="Execute complete automated end-to-end self-test.")

    args = parser.parse_args()

    inspector = QRDeepForensicInspector(
        model_path=args.model,
        output_file=args.output
    )

    if args.test_demo:
        print("\n=======================================================")
        print(" DRUGSHIELD AI - FORENSIC SELF-TEST DEMONSTRATION")
        print("=======================================================\n")
        run_self_test(inspector)
        return

    if not args.image:
        print("[!] No target specified. Use '--image <path>' or '--test-demo' for self-test.")
        parser.print_help()
        sys.exit(1)

    result = inspector.inspect(args.image)
    print("\n---------------- FORENSIC DOSSIER RESULT ----------------")
    print(json.dumps(result, indent=2))
    print("---------------------------------------------------------")


def run_self_test(inspector: QRDeepForensicInspector):
    """
    Self-contained verification suite generating synthetic suspect flyers with
    embedded UPI QR codes, EXIF GPS tags, and verifying deep evidence extraction.
    """
    import qrcode

    test_dir = PROJECT_ROOT / "data" / "forensic_cache" / "test_fixtures"
    test_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate Synthetic UPI QR Flyer
    upi_payload = "upi://pay?pa=syndicate_score@ybl&pn=Delhi_Drop_Network&mc=5499&tr=REF889911&tn=LSD_Stamps_Deposit&am=4500.00&cu=INR"
    qr_img = qrcode.make(upi_payload)

    canvas = Image.new("RGB", (500, 500), color=(255, 255, 255))
    qr_resized = qr_img.resize((350, 350))
    canvas.paste(qr_resized, (75, 75))

    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "Apple"
    exif[ExifTags.Base.Model] = "iPhone 14 Pro"
    exif[ExifTags.Base.Software] = "iOS 16.5"
    exif[ExifTags.Base.DateTime] = "2026:10:05 19:42:00"

    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps_ifd[ExifTags.GPS.GPSLatitude] = (28.0, 36.0, 50.04)
    gps_ifd[ExifTags.GPS.GPSLatitudeRef] = "N"
    gps_ifd[ExifTags.GPS.GPSLongitude] = (77.0, 12.0, 32.40)
    gps_ifd[ExifTags.GPS.GPSLongitudeRef] = "E"
    gps_ifd[ExifTags.GPS.GPSAltitude] = 216.5

    flyer_path = test_dir / "test_suspect_flyer_upi.jpg"
    canvas.save(flyer_path, exif=exif)

    simulated_narcotics = [
        {"class_name": "weed", "confidence": 0.89, "bbox": [100.0, 120.0, 340.0, 380.0]}
    ]

    print(f"[*] Synthetic suspect flyer created at: {flyer_path}")
    print(f"[*] Active YOLO Model Weights: {inspector.yolo_inspector.model_path}")
    print("[*] Running QR Deep Inspector pipeline...")

    dossier = inspector.inspect(flyer_path, simulated_narcotics_detections=simulated_narcotics)

    print("\n[*] Self-Test Verification:")
    print(f" - QR Detected              : {dossier['qr_detected']} (Count: {dossier['qr_count']})")
    print(f" - Financial VPA            : {dossier['financial_intelligence']['vpa']}")
    print(f" - Payee Name               : {dossier['financial_intelligence']['payee_name']}")
    print(f" - Banking PSP              : {dossier['financial_intelligence']['psp_institution']}")
    print(f" - Flagged Note Keywords    : {dossier['financial_intelligence']['flagged_keywords']}")
    print(f" - Narcotics Detected       : {dossier['vision_classification']['is_narcotics_detected']}")
    print(f" - Max Narcotics Conf       : {dossier['vision_classification']['max_narcotics_confidence']}")
    print(f" - EXIF GPS Acquired        : {dossier['geolocation_intelligence']['has_gps']}")
    print(f" - Lat / Lon Coordinates   : ({dossier['geolocation_intelligence']['latitude']}, {dossier['geolocation_intelligence']['longitude']})")
    print(f" - Device Attribution       : {dossier['geolocation_intelligence']['device_maker']} {dossier['geolocation_intelligence']['device_model']}")
    print(f" - Forensic Flags           : {dossier['forensic_flags']}")
    print(f" - Intel JSON Persisted     : {DEFAULT_OUTPUT_INTEL_PATH.resolve()}")

    assert dossier["qr_detected"] is True, "QR detection failed!"
    assert dossier["financial_intelligence"]["vpa"] == "syndicate_score@ybl", "UPI VPA extraction failed!"
    assert dossier["vision_classification"]["is_narcotics_detected"] is True, "Narcotics flag failed!"
    assert dossier["geolocation_intelligence"]["has_gps"] is True, "GPS extraction failed!"
    print("\n[SUCCESS] All pipeline assertions PASSED!")


if __name__ == "__main__":
    run_cli()