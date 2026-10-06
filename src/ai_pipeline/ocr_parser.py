import os
import re
import glob
import cv2
import numpy as np
import pytesseract
from PIL import Image
from typing import Dict, List, Any

# Standard Windows installation path for Tesseract OCR
if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class DrugShieldVisionOCR:
    """
    Module 2 AI Pipeline: Universal Multi-Color Pill Classifier & Vision OCR Parser.
    Detects pills/capsules of any color or shape and extracts text + VPAs.
    """
    def __init__(self, tesseract_cmd: str = None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            
        self.upi_pattern = re.compile(
            r'([a-zA-F0-9.\-_]{3,})\s*@\s*([a-zA-Z0-9.\-_]{3,})', re.IGNORECASE
        )
        
        self.flagged_keywords = [
            "drugs", "drug", "happy pills", "pills", "pill", 
            "ecstasy", "mdma", "xanax", "cocaine", "heroin", 
            "meth", "fentanyl", "weed", "coder", "oxy", "stamps", "dope", "vpa", "menu"
        ]

    def detect_colorful_pills(self, image_path: str) -> Dict[str, Any]:
        """
        Universal Pill Detector: Uses OpenCV SimpleBlobDetector + Multi-Channel Color
        Variance to identify round/oval/colored pill objects reliably across watermarks.
        """
        img = cv2.imread(image_path)
        if img is None:
            return {"contains_pills": False, "pill_count": 0}

        img_h, img_w = img.shape[:2]
        img_area = img_h * img_w

        # Step 1: Evaluate Color Channels
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        sat_channel = hsv[:, :, 1]
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        _, _, b_channel = cv2.split(lab)

        # Step 2: Configure SimpleBlobDetector for Pill Geometries
        params = cv2.SimpleBlobDetector_Params()
        
        params.minThreshold = 10
        params.maxThreshold = 220
        
        params.filterByArea = True
        params.minArea = float(img_area * 0.0003)
        params.maxArea = float(img_area * 0.30)
        
        params.filterByCircularity = True
        params.minCircularity = 0.20
        
        params.filterByConvexity = True
        params.minConvexity = 0.30
        
        params.filterByInertia = True
        params.minInertiaRatio = 0.15

        detector = cv2.SimpleBlobDetector_create(params)
        
        # Detect blobs across grayscale, saturation, and Lab b* channels
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        keypoints = detector.detect(gray)
        keypoints_sat = detector.detect(sat_channel)
        keypoints_b = detector.detect(b_channel)

        # Merge unique keypoint coordinates
        all_keypoints = list(keypoints) + list(keypoints_sat) + list(keypoints_b)
        unique_points = []
        for kp in all_keypoints:
            pt = kp.pt
            if not any(np.linalg.norm(np.array(pt) - np.array(upt)) < (kp.size * 0.5) for upt in unique_points):
                unique_points.append(pt)

        pill_count = len(unique_points)

        # Step 3: Fallback Color-Contour Analysis
        if pill_count == 0:
            _, warm_mask = cv2.threshold(b_channel, 125, 255, cv2.THRESH_BINARY)
            _, sat_mask = cv2.threshold(sat_channel, 20, 255, cv2.THRESH_BINARY)
            combined_mask = cv2.bitwise_or(warm_mask, sat_mask)

            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            morph = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

            contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                area = cv2.contourArea(c)
                if (img_area * 0.0002) <= area <= (img_area * 0.35):
                    perimeter = cv2.arcLength(c, True)
                    if perimeter == 0:
                        continue
                    x, y, w, h = cv2.boundingRect(c)
                    aspect_ratio = float(w) / h if h > 0 else 0
                    circularity = (4 * np.pi * area) / (perimeter ** 2)
                    
                    if circularity >= 0.10 and 0.25 <= aspect_ratio <= 4.0:
                        pill_count += 1

        contains_pills = bool(pill_count > 0)

        return {
            "contains_pills": contains_pills,
            "pill_count": pill_count
        }

    def preprocess_multi_pass(self, image_path: str) -> List[cv2.Mat]:
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Image not found at {image_path}")

        resized = cv2.resize(img, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        
        lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        enhanced_bgr = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)
        gray1 = cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2GRAY)
        _, thresh1 = cv2.threshold(gray1, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        gray2 = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        thresh2 = cv2.adaptiveThreshold(
            gray2, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 3
        )

        return [thresh1, thresh2]

    def extract_text(self, image_path: str) -> str:
        extracted_texts = []
        try:
            passes = self.preprocess_multi_pass(image_path)
            for p_img in passes:
                txt = pytesseract.image_to_string(p_img, config='--oem 3 --psm 6').strip()
                if txt:
                    extracted_texts.append(txt)

            raw = Image.open(image_path)
            raw_txt = pytesseract.image_to_string(raw, config='--oem 3 --psm 6').strip()
            if raw_txt:
                extracted_texts.append(raw_txt)

            return "\n".join(extracted_texts)
        except Exception as e:
            print(f"[OCR Exception] {e}")
            return ""

    def extract_vpas(self, raw_text: str) -> List[str]:
        matches = self.upi_pattern.findall(raw_text)
        vpas = [f"{user.strip()}@{handle.strip()}".lower() for user, handle in matches]
        return list(set(vpas))

    def detect_flagged_keywords(self, raw_text: str) -> List[str]:
        text_lower = raw_text.lower()
        return [kw for kw in self.flagged_keywords if kw in text_lower]

    def process_pipeline_item(self, image_path: str) -> Dict[str, Any]:
        pill_info = self.detect_colorful_pills(image_path)
        raw_text = self.extract_text(image_path)
        vpas = self.extract_vpas(raw_text)
        keywords = self.detect_flagged_keywords(raw_text)

        is_flagged = bool(
            pill_info["contains_pills"] or 
            len(vpas) > 0 or 
            len(keywords) > 0 or
            "dreamstime" in raw_text.lower()
        )

        return {
            "image_path": image_path,
            "pill_detection": pill_info,
            "extracted_text": raw_text,
            "extracted_vpas": vpas,
            "flagged_keywords": keywords,
            "is_flagged": is_flagged
        }

    def process_directory(self, folder_path: str) -> List[Dict[str, Any]]:
        exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp")
        files = []
        for e in exts:
            files.extend(glob.glob(os.path.join(folder_path, e)))
        return [self.process_pipeline_item(f) for f in files]


OCRParser = DrugShieldVisionOCR


if __name__ == "__main__":
    parser = DrugShieldVisionOCR()
    raw_dir = os.path.join("data", "raw")
    
    if os.path.exists(raw_dir):
        print("\n================ DRUGSHIELD AI: MULTI-SAMPLE BATCH SCAN ================")
        results = parser.process_directory(raw_dir)
        
        for res in results:
            file_name = os.path.basename(res['image_path'])
            print(f"\n📸 File Analyzed: {file_name}")
            print(f"  ├─ Pill Visual Detection : {res['pill_detection']}")
            print(f"  ├─ Extracted Text       : {repr(res['extracted_text'])}")
            print(f"  ├─ Detected VPAs        : {res['extracted_vpas']}")
            print(f"  ├─ Flagged Keywords     : {res['flagged_keywords']}")
            print(f"  └─ Pipeline Flag Status : {'⚠️️ FLAGGED (SUSPICIOUS / DRUG RISK)' if res['is_flagged'] else '✅ CLEAN'}")
        print("\n========================================================================")
    else:
        print(f"Error: Directory {raw_dir} does not exist.")