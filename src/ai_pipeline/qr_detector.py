"""Decode QR payloads from message attachments; this module does not score risk."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import zxingcpp
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

ImageInput = Union[str, Path, bytes, bytearray, np.ndarray, Image.Image]


class QRCodeDecoder:
    """Decode QR codes with ZXing-C++ and return payloads as evidence only.

    URLs are never opened. This class does not decide whether a payload or
    message is suspicious and does not require a trained QR model.
    """

    def decode(self, image_input: ImageInput) -> Dict[str, Any]:
        image, source_name, source_hash, load_error = self._load_image(image_input)
        if image is None:
            return self._result(
                source_name=source_name,
                source_hash=source_hash,
                error=load_error or "image_decode_failed",
            )

        codes: List[Dict[str, Any]] = []
        regions: List[Dict[str, Any]] = []
        seen_payloads = set()
        seen_regions = set()
        decode_errors = []

        # Keep the original first. Try bounded recovery variants only if needed.
        for variant_name, candidate in self._recovery_variants(image):
            try:
                barcodes = zxingcpp.read_barcodes(
                    candidate,
                    formats=zxingcpp.BarcodeFormat.QRCode,
                    try_rotate=True,
                    try_downscale=True,
                    try_invert=True,
                    return_errors=True,
                )
            except (RuntimeError, TypeError, ValueError) as exc:
                decode_errors.append(str(exc))
                continue

            for barcode in barcodes:
                # Only coordinates from the original image are source coordinates.
                bbox = self._bbox(barcode.position) if variant_name == "original" else None
                if bbox:
                    bbox_key = tuple(bbox)
                    if bbox_key not in seen_regions:
                        regions.append({"bbox": bbox, "engine": "zxing-cpp"})
                        seen_regions.add(bbox_key)

                payload = barcode.text or ""
                if payload and payload not in seen_payloads:
                    codes.append({
                        "payload": payload,
                        "bbox": bbox,
                        "engine": "zxing-cpp",
                        "decode_variant": variant_name,
                    })
                    seen_payloads.add(payload)
            if codes:
                break

        # Detection is evidence of a QR region, not evidence that its payload
        # was recovered. Preserve this distinction for human review.
        if not regions:
            bbox = self._detect_qr_region(image)
            if bbox:
                regions.append({"bbox": bbox, "engine": "opencv-detection-only"})

        return self._result(
            source_name=source_name,
            source_hash=source_hash,
            codes=codes,
            detected_regions=regions,
            error=(f"qr_decode_failed: {decode_errors[-1]}" if decode_errors and not codes else None),
        )

    @staticmethod
    def _recovery_variants(image: Any) -> List[Tuple[str, Any]]:
        """Create a small set of preprocessing variants for common image defects."""
        try:
            pil_image = image if isinstance(image, Image.Image) else Image.fromarray(image)
            gray = ImageOps.grayscale(pil_image)
            enhanced = ImageOps.autocontrast(gray, cutoff=1)
            enhanced = ImageEnhance.Contrast(enhanced).enhance(1.5)
            sharpened = enhanced.filter(
                ImageFilter.UnsharpMask(radius=2, percent=160, threshold=3)
            )
            variants: List[Tuple[str, Any]] = [("original", image)]
            rectified = QRCodeDecoder._rectify_detected_qr(image)
            if rectified is not None:
                variants.append(("perspective_rectified", rectified))
            variants.append(("contrast_sharpen", sharpened))

            width, height = sharpened.size
            scale = min(3.0, 1600 / max(width, height))
            if scale > 1.15:
                variants.append((
                    "upscaled",
                    sharpened.resize(
                        (int(width * scale), int(height * scale)),
                        Image.Resampling.LANCZOS,
                    ),
                ))

            # Thresholding can help faded codes against uneven backgrounds.
            threshold = sharpened.point(lambda value: 255 if value >= 150 else 0)
            variants.append(("threshold", threshold))
            return variants
        except (TypeError, ValueError, OSError):
            return [("original", image)]

    @staticmethod
    def _rectify_detected_qr(image: Any) -> Optional[Any]:
        """Perspective-correct a detected QR quadrilateral for another decode pass."""
        try:
            import cv2

            array = np.asarray(image)
            found, points = cv2.QRCodeDetector().detect(array)
            if not found or points is None:
                return None
            corners = points.reshape(4, 2).astype(np.float32)
            top = np.linalg.norm(corners[1] - corners[0])
            bottom = np.linalg.norm(corners[2] - corners[3])
            left = np.linalg.norm(corners[3] - corners[0])
            right = np.linalg.norm(corners[2] - corners[1])
            side = int(max(top, bottom, left, right))
            if side < 32:
                return None
            destination = np.array(
                [[0, 0], [side - 1, 0], [side - 1, side - 1], [0, side - 1]],
                dtype=np.float32,
            )
            transform = cv2.getPerspectiveTransform(corners, destination)
            return cv2.warpPerspective(
                array, transform, (side, side), borderMode=cv2.BORDER_REPLICATE
            )
        except Exception:
            # Rectification is an optional recovery path; decoding the original
            # and ordinary image variants must remain available on every build.
            return None

    @staticmethod
    def _detect_qr_region(image: Any) -> Optional[List[int]]:
        """Locate QR corners when possible, without claiming payload decoding."""
        try:
            import cv2

            found, points = cv2.QRCodeDetector().detect(np.asarray(image))
            if not found or points is None:
                return None
            points = points.reshape(-1, 2)
            return [
                int(points[:, 0].min()), int(points[:, 1].min()),
                int(points[:, 0].max()), int(points[:, 1].max()),
            ]
        except (ImportError, ValueError):
            return None
        except Exception:
            # OpenCV's optional detector varies by build and input format.
            return None

    @staticmethod
    def _load_image(
        image_input: ImageInput,
    ) -> Tuple[Optional[Any], str, Optional[str], Optional[str]]:
        source_name = "in_memory_image"
        raw_bytes: Optional[bytes] = None

        try:
            if isinstance(image_input, (str, Path)):
                path = Path(image_input)
                source_name = str(path)
                if not path.is_file():
                    return None, source_name, None, "image_not_found"
                raw_bytes = path.read_bytes()
                image = Image.open(io.BytesIO(raw_bytes))
                image = ImageOps.exif_transpose(image).convert("RGB")
                return image, source_name, _sha256(raw_bytes), None

            if isinstance(image_input, (bytes, bytearray)):
                raw_bytes = bytes(image_input)
                image = Image.open(io.BytesIO(raw_bytes))
                image = ImageOps.exif_transpose(image).convert("RGB")
                return image, source_name, _sha256(raw_bytes), None

            if isinstance(image_input, Image.Image):
                image = ImageOps.exif_transpose(image_input).convert("RGB")
                raw_bytes = image.tobytes()
                return image, source_name, _sha256(raw_bytes), None

            if isinstance(image_input, np.ndarray):
                image = np.asarray(image_input)
                if image.size == 0 or image.ndim not in (2, 3):
                    return None, source_name, None, "invalid_image"
                if image.dtype != np.uint8:
                    image = np.clip(image, 0, 255).astype(np.uint8)
                image = np.ascontiguousarray(image)
                raw_bytes = image.tobytes()
                return image, source_name, _sha256(raw_bytes), None

            return None, source_name, None, "unsupported_image_input"
        except (OSError, UnidentifiedImageError, TypeError, ValueError) as exc:
            return None, source_name, _sha256(raw_bytes), f"image_read_failed: {exc}"

    @staticmethod
    def _bbox(position: Any) -> Optional[List[int]]:
        if position is None:
            return None
        points = []
        for name in ("top_left", "top_right", "bottom_right", "bottom_left"):
            point = getattr(position, name, None)
            if point is not None:
                points.append((float(point.x), float(point.y)))
        if not points:
            return None
        xs, ys = zip(*points)
        return [
            int(min(xs)),
            int(min(ys)),
            int(max(xs)),
            int(max(ys)),
        ]

    @staticmethod
    def _result(
        source_name: str,
        source_hash: Optional[str],
        codes: Optional[List[Dict[str, Any]]] = None,
        detected_regions: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        codes = codes or []
        detected_regions = detected_regions or []
        return {
            "qr_detected": bool(codes or detected_regions),
            "qr_decoded": bool(codes),
            "payload_raw": codes[0]["payload"] if codes else None,
            "all_decoded_codes": codes,
            "detected_regions": detected_regions,
            "source_image": source_name,
            "source_sha256": source_hash,
            "engine_used": codes[0]["engine"] if codes else None,
            "bbox": (
                codes[0]["bbox"]
                if codes
                else detected_regions[0]["bbox"] if detected_regions else None
            ),
            "error": error,
        }


def _sha256(data: Optional[bytes]) -> Optional[str]:
    return hashlib.sha256(data).hexdigest() if data is not None else None


_GLOBAL_DECODER: Optional[QRCodeDecoder] = None


def get_qr_decoder() -> QRCodeDecoder:
    """Return the shared decoder instance."""
    global _GLOBAL_DECODER
    if _GLOBAL_DECODER is None:
        _GLOBAL_DECODER = QRCodeDecoder()
    return _GLOBAL_DECODER


def scan_qr_payload(image_input: ImageInput) -> Dict[str, Any]:
    """Decode QR payloads from an image path, image bytes, or image object."""
    return get_qr_decoder().decode(image_input)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Decode QR payloads from an image")
    parser.add_argument("--image", required=True, help="Image path to inspect")
    args = parser.parse_args()
    print(json.dumps(scan_qr_payload(args.image), indent=2, ensure_ascii=False))
