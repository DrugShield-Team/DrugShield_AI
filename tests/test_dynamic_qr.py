# tests/test_dynamic_qr.py
"""
DrugShield AI - Dynamic QR Generator & Forensic Threat Testing Tool
===================================================================
Allows testing the QR detection and threat evaluation pipeline with dynamic,
custom, or randomized payloads on-the-fly.

Usage:
  1. Test custom payload:
     python tests/test_dynamic_qr.py --payload "MDMA 2g 5k menu DM @plug_bot"

  2. Test a custom image file:
     python tests/test_dynamic_qr.py --image path/to/my_flyer.jpg

  3. Run randomized dynamic scenario generator:
     python tests/test_dynamic_qr.py --random

  4. Interactive prompt mode:
     python tests/test_dynamic_qr.py
"""

import sys
import json
import random
from pathlib import Path
from datetime import datetime
import qrcode
from PIL import Image, ImageDraw, ImageFont

# Project root hook
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_pipeline.qr_detector import scan_qr_payload, get_qr_detector

FIXTURES_DIR = PROJECT_ROOT / "data" / "forensic_cache" / "test_fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def generate_qr_image(payload: str, output_filename: str = None, embed_in_flyer: bool = True) -> Path:
    """
    Generates a QR code image from any dynamic payload string.
    Optionally embeds the QR into a simulated flyer canvas with headers.
    """
    if not output_filename:
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        rand_id = random.randint(100, 999)
        output_filename = f"dynamic_qr_{timestamp_str}_{rand_id}.png"

    out_path = FIXTURES_DIR / output_filename

    # Generate QR matrix
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    if not embed_in_flyer:
        qr_img.save(str(out_path))
        return out_path

    # Embed QR into a realistic flyer canvas
    canvas_w, canvas_h = 600, 750
    flyer = Image.new("RGB", (canvas_w, canvas_h), color=(245, 245, 250))
    draw = ImageDraw.Draw(flyer)

    # Flyer Header Background
    draw.rectangle([(0, 0), (canvas_w, 80)], fill=(30, 41, 59))
    draw.text((20, 28), "DRUGSHIELD FORENSIC EVIDENCE DISK - INGESTION TEST", fill=(255, 255, 255))

    # Center QR code
    qr_w, qr_h = qr_img.size
    qr_scaled = qr_img.resize((380, 380))
    paste_x = (canvas_w - 380) // 2
    paste_y = 130
    flyer.paste(qr_scaled, (paste_x, paste_y))

    # Footer note
    draw.rectangle([(0, 680), (canvas_w, canvas_h)], fill=(226, 232, 240))
    draw.text((20, 705), f"Sample Payload Tag: {payload[:55]}...", fill=(71, 85, 105))

    flyer.save(str(out_path))
    return out_path


def run_dynamic_test(payload: str, label: str = "Custom Dynamic Payload") -> dict:
    """Generates QR on the fly, executes the detection pipeline, and prints forensic report."""
    print("\n" + "=" * 70)
    print(f"[*] TESTING SCENARIO: {label}")
    print("=" * 70)
    print(f"Dynamic Payload Input:\n    {payload}\n")

    # 1. Generate image
    img_path = generate_qr_image(payload)
    print(f"[+] Generated flyer with QR code at:\n    {img_path.resolve()}\n")

    # 2. Scan using the pipeline runner
    print("[*] Running scan_qr_payload()...")
    result = scan_qr_payload(str(img_path))

    # 3. Display structured forensic output
    status = result.get("status")
    conf = result.get("confidence_score")
    color_tag = "🔴" if status == "DRUG_DETECTED" else ("🟡" if status == "SUSPICIOUS" else "🟢")

    print(f"\n{color_tag} FORENSIC PIPELINE SCAN RESULT:")
    print(f"    - Status          : {status}")
    print(f"    - Confidence Score: {conf}")
    print(f"    - QR Detected     : {result.get('qr_detected')}")
    print(f"    - Engine Used     : {result.get('engine_used')}")
    print(f"    - Decoded Payload : {result.get('payload_raw')}")
    print(f"    - Keywords        : {result.get('extracted_keywords')}")
    print(f"    - Indicators      : {result.get('threat_indicators')}")
    print(f"    - Cached QR Crop  : {result.get('crop_path')}")
    print(f"    - Evidence ID     : {result.get('evidence_id')}")
    print(f"    - Intelligence DB : data/qr_deep_intel.json (updated)")
    print("=" * 70 + "\n")

    return result


def generate_random_scenario():
    """Generates a dynamic randomized payload across different threat categories."""
    scenarios = [
        # Scenario 1: Hard drug menu
        (
            "Hard Narcotics Menu & Telegram Bot",
            lambda: f"Fresh stock {random.choice(['MDMA', 'Cocaine', 'Meth', 'Heroin', 'Ketamine'])} {random.choice(['1g', '2g', '5g', '10g'])} "
                    f"rates list. Fast stealth delivery. DM @party_supplies_{random.randint(10,99)}_bot UPI plug_{random.randint(100,999)}@ybl"
        ),
        # Scenario 2: Prescription pills
        (
            "Prescription Narcotics Solicitation",
            lambda: f"Original {random.choice(['Xanax', 'Tramadol', 'Oxycodone', 'Adderall', 'Valium'])} pills & bars in stock. "
                    f"Vacuum sealed courier. Order here cash on drop."
        ),
        # Scenario 3: Encrypted redirect / Wickr / Signal
        (
            "Encrypted Messaging Redirect (Suspicious)",
            lambda: f"Secret drop communications. Connect on {random.choice(['Wickr: anon_drop_', 'Signal: +91987654', 'https://t.me/delhi_dead_drop_'])}"
                    f"{random.randint(1000, 9999)}"
        ),
        # Scenario 4: Dead drop coordinates
        (
            "Dead Drop GPS Coordinates",
            lambda: f"Package placed at dead drop coordinates: 28.{random.randint(5000, 7000)}, 77.{random.randint(1000, 3000)}. Token amount confirmed."
        ),
        # Scenario 5: Darknet Mirror
        (
            "Darknet Tor .onion Mirror",
            lambda: f"http://darkmarket_{random.randint(10000,99999)}_catalog.onion/order?ref=vault"
        ),
        # Scenario 6: Benign / Clean URL
        (
            "Clean / Benign Web Link",
            lambda: f"https://www.medicalresearch.org/study?id={random.randint(1000, 9999)}&topic=chemistry"
        ),
        # Scenario 7: Standard UPI Payment (Benign / Clean)
        (
            "Legitimate UPI Payment QR",
            lambda: f"upi://pay?pa=grocery_store_{random.randint(10,99)}@okhdfcbank&pn=Daily_Supermarket&mc=5411&am={random.randint(50, 500)}.00&cu=INR"
        ),
    ]

    label, generator_fn = random.choice(scenarios)
    return label, generator_fn()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DrugShield AI - Dynamic QR Threat Tester")
    parser.add_argument("--payload", "-p", type=str, help="Custom text, URL, or UPI string to encode into QR and test")
    parser.add_argument("--image", "-i", type=str, help="Existing image file path to scan with the pipeline")
    parser.add_argument("--random", "-r", action="store_true", help="Generate and test a randomized dynamic scenario")
    parser.add_argument("--batch", "-b", type=int, default=0, help="Run N dynamic randomized scenarios in sequence")
    args = parser.parse_args()

    if args.payload:
        run_dynamic_test(args.payload, label="User Provided Dynamic Payload")

    elif args.image:
        print(f"[*] Scanning existing image file: {args.image}")
        res = scan_qr_payload(args.image)
        print(json.dumps(res, indent=2))

    elif args.batch > 0:
        print(f"\n[*] Executing {args.batch} dynamic test scenarios...\n")
        for i in range(1, args.batch + 1):
            lbl, pld = generate_random_scenario()
            run_dynamic_test(pld, label=f"Batch Test {i}/{args.batch}: {lbl}")

    elif args.random:
        lbl, pld = generate_random_scenario()
        run_dynamic_test(pld, label=lbl)

    else:
        # Interactive mode
        print("\n" + "=" * 65)
        print("  DRUGSHIELD AI - INTERACTIVE DYNAMIC QR TESTER ")
        print("=" * 65)
        print("Enter any text, URL, or UPI payload below to generate a QR")
        print("and run the deep forensic detection pipeline.")
        print("(Press Enter with empty input to run a randomized scenario)\n")

        try:
            user_input = input("Enter payload > ").strip()
        except EOFError:
            user_input = ""

        if user_input:
            run_dynamic_test(user_input, label="Interactive User Input")
        else:
            lbl, pld = generate_random_scenario()
            run_dynamic_test(pld, label=f"Randomized Scenario: {lbl}")
