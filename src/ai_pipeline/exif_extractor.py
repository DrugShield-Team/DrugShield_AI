"""
DrugShield AI - Media Forensics: EXIF & GPS Metadata Extractor
=============================================================
Extracts hardware specifications, capture timestamps, and embedded
GPS coordinates (DMS -> Decimal Degrees) from evidence images uploaded
by targets or intercepted during simulation crawling.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
from PIL import Image, ExifTags

logger = logging.getLogger("DrugShield.EXIFExtractor")

# Map integer tag IDs to human-readable tag names
TAGS = ExifTags.TAGS
GPSTAGS = ExifTags.GPSTAGS


def _dms_to_decimal(dms: Tuple[Any, Any, Any], ref: str) -> Optional[float]:
    """Convert Degrees/Minutes/Seconds tuple with hemisphere reference to Decimal Degrees."""
    try:
        def _to_float(v: Any) -> float:
            if hasattr(v, "numerator") and hasattr(v, "denominator"):
                return float(v.numerator) / float(v.denominator) if v.denominator != 0 else 0.0
            return float(v)

        degrees = _to_float(dms[0])
        minutes = _to_float(dms[1])
        seconds = _to_float(dms[2])

        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref.upper() in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except Exception as e:
        logger.debug(f"Failed to convert DMS {dms} with ref {ref}: {e}")
        return None


def extract_exif_metadata(image_input: Union[str, Path, bytes, Image.Image]) -> Dict[str, Any]:
    """
    Extract camera specifications, software, timestamps, and GPS coordinates from an image.
    Never alters or re-saves the input image.
    """
    result: Dict[str, Any] = {
        "has_exif": False,
        "has_gps": False,
        "latitude": None,
        "longitude": None,
        "altitude": None,
        "device_make": None,
        "device_model": None,
        "software": None,
        "timestamp": None,
        "lens_model": None,
        "raw_tags": {},
    }

    image = None
    try:
        if isinstance(image_input, (str, Path)):
            path = Path(image_input)
            if not path.is_file():
                return result
            image = Image.open(path)
        elif isinstance(image_input, Image.Image):
            image = image_input
        elif isinstance(image_input, (bytes, bytearray)):
            import io
            image = Image.open(io.BytesIO(image_input))
        else:
            return result

        raw_exif = image.getexif()
        if not raw_exif:
            return result

        result["has_exif"] = True
        gps_info: Dict[str, Any] = {}

        # Parse primary EXIF tags
        for tag_id, value in raw_exif.items():
            tag_name = TAGS.get(tag_id, str(tag_id))
            if tag_name == "Make":
                result["device_make"] = str(value).strip()
            elif tag_name == "Model":
                result["device_model"] = str(value).strip()
            elif tag_name == "Software":
                result["software"] = str(value).strip()
            elif tag_name in ("DateTime", "DateTimeOriginal"):
                result["timestamp"] = str(value).strip()
            elif tag_name == "LensModel":
                result["lens_model"] = str(value).strip()
            elif tag_name == "GPSInfo":
                gps_info = value

            if isinstance(value, (int, float, str)):
                result["raw_tags"][tag_name] = value

        # Parse GPS IFD tags if present
        # In Pillow, GPS IFD can be in get_ifd(ExifTags.IFD.GPSInfo) or raw_exif[GPSInfo]
        if hasattr(raw_exif, "get_ifd"):
            try:
                gps_ifd = raw_exif.get_ifd(ExifTags.IFD.GPSInfo)
                if gps_ifd:
                    for k, v in gps_ifd.items():
                        gps_info[GPSTAGS.get(k, str(k))] = v
            except Exception:
                pass

        if isinstance(gps_info, dict):
            # Resolve GPS coordinates
            lat_dms = gps_info.get("GPSLatitude")
            lat_ref = gps_info.get("GPSLatitudeRef", "N")
            lon_dms = gps_info.get("GPSLongitude")
            lon_ref = gps_info.get("GPSLongitudeRef", "E")

            if lat_dms and lon_dms:
                lat = _dms_to_decimal(lat_dms, str(lat_ref))
                lon = _dms_to_decimal(lon_dms, str(lon_ref))
                if lat is not None and lon is not None:
                    result["has_gps"] = True
                    result["latitude"] = lat
                    result["longitude"] = lon

            alt = gps_info.get("GPSAltitude")
            if alt is not None:
                try:
                    if hasattr(alt, "numerator") and hasattr(alt, "denominator"):
                        result["altitude"] = round(float(alt.numerator) / float(alt.denominator), 2)
                    else:
                        result["altitude"] = round(float(alt), 2)
                except Exception:
                    pass

    except Exception as exc:
        logger.warning(f"EXIF parsing encountered error: {exc}")
    finally:
        if image and isinstance(image_input, (str, Path)):
            try:
                image.close()
            except Exception:
                pass

    return result
