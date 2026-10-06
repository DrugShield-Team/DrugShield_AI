import json
import inspect
import asyncio
from pathlib import Path

try:
    from src.ingestion import telegram_listener
except (ImportError, Exception):
    telegram_listener = None

try:
    from src.ingestion import instagram_crawler
except (ImportError, Exception):
    instagram_crawler = None

try:
    from src.ingestion import whatsapp_feed
except (ImportError, Exception):
    whatsapp_feed = None

from src.ai_pipeline.qr_detector import scan_qr_payload

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
IMAGES_DIR = RAW_DIR / "images"

def init_raw_landing_zone():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

async def call_module_entry(mod):
    if not mod:
        return None
    possible_names = [
        "run_instagram_crawler",
        "run_telegram_crawler",
        "scrape_whatsapp_feed",
        "main",
        "run",
        "crawl",
        "scrape",
    ]

    for fn_name in possible_names:
        fn = getattr(mod, fn_name, None)

        if callable(fn):
            result = fn()

            if inspect.isawaitable(result):
                result = await result

            return result

    return None

async def collect_all_crawlers():
    all_records = []

    # Telegram: guarantee 1 record
    try:
        tg_data = await call_module_entry(telegram_listener)
        tg_records = tg_data if isinstance(tg_data, list) else [tg_data] if isinstance(tg_data, dict) else []

        if tg_records:
            all_records.extend(tg_records[:1])
        else:
            all_records.append({
                "platform": "Telegram",
                "status": "unavailable",
                "is_fallback_mock": True
            })
    except Exception as e:
        print(f"[Pipeline Notice] Telegram error: {e}")
        all_records.append({
            "platform": "Telegram",
            "status": "error",
            "is_fallback_mock": True
        })

    # Instagram: guarantee 2 records
    try:
        ig_data = await call_module_entry(instagram_crawler)
        ig_records = ig_data if isinstance(ig_data, list) else [ig_data] if isinstance(ig_data, dict) else []

        all_records.extend(ig_records[:2])

        while len(ig_records) < 2:
            all_records.append({
                "platform": "Instagram",
                "scrape_type": "profile" if len(ig_records) == 0 else "hashtag",
                "status": "unavailable",
                "is_fallback_mock": True
            })
            ig_records.append({})
    except Exception as e:
        print(f"[Pipeline Notice] Instagram error: {e}")
        all_records.extend([
            {
                "platform": "Instagram",
                "scrape_type": "profile",
                "status": "error",
                "is_fallback_mock": True
            },
            {
                "platform": "Instagram",
                "scrape_type": "hashtag",
                "status": "error",
                "is_fallback_mock": True
            }
        ])

    # WhatsApp: guarantee 6 records
    try:
        wa_data = await call_module_entry(whatsapp_feed)
        wa_records = wa_data if isinstance(wa_data, list) else []

        if not wa_records:
            wa_file = BASE_DIR / "src" / "data.json"
            if wa_file.exists():
                with open(wa_file, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    if isinstance(loaded_data, list):
                        wa_records = loaded_data

        all_records.extend(wa_records[:6])

        while len(wa_records) < 6:
            all_records.append({
                "platform": "WhatsApp",
                "status": "unavailable",
                "is_fallback_mock": True
            })
            wa_records.append({})
    except Exception as e:
        print(f"[Pipeline Notice] WhatsApp error: {e}")
        all_records.extend([
            {
                "platform": "WhatsApp",
                "status": "error",
                "is_fallback_mock": True
            }
            for _ in range(6)
        ])

    return all_records[:9]

def process_qr_intelligence(records):
    """
    Scans media attachments in ingested crawler records and local landing zone images
    for QR codes, analyzing decoded payloads for narcotics & contraband threats.
    """
    print("\n--------------------------------------------------")
    print("      DRUGSHIELD AI - QR FORENSICS PIPELINE       ")
    print("--------------------------------------------------")

    scanned_count = 0
    flagged_threats = 0
    scanned_paths = set()

    # 1. Inspect records that have media_path
    for rec in records:
        m_path = rec.get("media_path")
        if m_path:
            candidates = [
                Path(m_path),
                RAW_DIR / Path(m_path).name,
                IMAGES_DIR / Path(m_path).name,
            ]
            valid_path = next((p for p in candidates if p.is_file()), None)
            if valid_path:
                abs_key = str(valid_path.resolve())
                scanned_paths.add(abs_key)
                scanned_count += 1
                try:
                    res = scan_qr_payload(str(valid_path))
                    rec["qr_scan"] = res
                    if res.get("qr_detected"):
                        print(f" [!] QR Detected in {valid_path.name}: Status={res['status']} | Threat={res['confidence_score']}")
                        if res.get("status") in ("DRUG_DETECTED", "SUSPICIOUS"):
                            flagged_threats += 1
                except Exception as e:
                    print(f" [-] Error scanning QR in {valid_path.name}: {e}")

    # 2. Inspect any additional images placed in RAW_DIR and IMAGES_DIR
    for folder in [IMAGES_DIR, RAW_DIR]:
        if folder.exists():
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                for img_file in folder.glob(ext):
                    abs_key = str(img_file.resolve())
                    if abs_key not in scanned_paths:
                        scanned_paths.add(abs_key)
                        scanned_count += 1
                        try:
                            res = scan_qr_payload(str(img_file))
                            if res.get("qr_detected"):
                                print(f" [!] QR Detected in {img_file.name}: Status={res['status']} | Threat={res['confidence_score']}")
                                if res.get("status") in ("DRUG_DETECTED", "SUSPICIOUS"):
                                    flagged_threats += 1
                        except Exception as e:
                            print(f" [-] Error scanning QR in {img_file.name}: {e}")

    print(f"Total Images Scanned for QR: {scanned_count}")
    print(f"Threats Flagged (DRUG/SUSP): {flagged_threats}")
    print("--------------------------------------------------\n")

def write_to_landing_zone(records):
    init_raw_landing_zone()
    process_qr_intelligence(records)
    output_path = RAW_DIR / "ingested_raw_data.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

    print("\n==================================================")
    print("      CENTRAL RAW LANDING ZONE STATUS             ")
    print("==================================================")
    print(f"Target Directory   : {RAW_DIR.resolve()}")
    print(f"Ingested JSON File : {output_path.name}")
    print(f"Total Raw Records  : {len(records)}")
    print("==================================================\n")

if __name__ == "__main__":
    init_raw_landing_zone()
    raw_records = asyncio.run(collect_all_crawlers())
    write_to_landing_zone(raw_records)