"""
DrugShield AI - Master Threat Intelligence Pipeline Controller
==============================================================
Orchestrates live ingestion from decoupled WhatsApp (Port 8090) and Telegram (Port 8000)
crawlers, routes live message streams through Module 2 (NLP & OCR) and Module 3 (UPI Parser),
evaluates dynamic threat scores, and coordinates Module 4 persistence & alert dispatch.
"""

import json
import inspect
import asyncio
from pathlib import Path

# Ingestion Modules
try:
    from src.ingestion import telegram_telegram as telegram_listener
except (ImportError, Exception):
    try:
        from src.ingestion import telegram_listener
    except (ImportError, Exception):
        telegram_listener = None

try:
    from src.ingestion import whatsapp_fast
except (ImportError, Exception):
    whatsapp_fast = None

try:
    from src.ingestion import instagram_crawler
except (ImportError, Exception):
    instagram_crawler = None

from src.ai_pipeline.qr_detector import scan_qr_payload
from src.ai_pipeline.threat_pipeline import evaluate_live_message_threat

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
        "run_telegram_crawler_async",
        "scrape_whatsapp_feed",
        "run_telegram_crawler",
        "run_whatsapp_fast",
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

    # 1. Telegram Live Simulation Crawler (Port 8000)
    try:
        tg_data = await call_module_entry(telegram_listener)
        tg_records = tg_data if isinstance(tg_data, list) else [tg_data] if isinstance(tg_data, dict) else []
        all_records.extend(tg_records)
        print(f"[Pipeline] Intercepted {len(tg_records)} live Telegram record(s).")
    except Exception as e:
        print(f"[Pipeline Notice] Telegram live crawler error: {e}")

    # 2. WhatsApp Live Simulation Crawler (Port 8090)
    try:
        wa_data = await call_module_entry(whatsapp_fast)
        wa_records = wa_data if isinstance(wa_data, list) else [wa_data] if isinstance(wa_data, dict) else []
        all_records.extend(wa_records)
        print(f"[Pipeline] Intercepted {len(wa_records)} live WhatsApp record(s).")
    except Exception as e:
        print(f"[Pipeline Notice] WhatsApp live crawler error: {e}")

    # 3. Instagram Crawler (Optional ancillary OSINT source)
    if instagram_crawler:
        try:
            ig_data = await call_module_entry(instagram_crawler)
            ig_records = ig_data if isinstance(ig_data, list) else [ig_data] if isinstance(ig_data, dict) else []
            all_records.extend(ig_records[:2])
        except Exception as e:
            print(f"[Pipeline Notice] Instagram crawler notice: {e}")

    return all_records


def process_threat_pipeline(records):
    """
    Executes Module 2 & Module 3 active threat evaluation on all intercepted records.
    """
    print("\n--------------------------------------------------")
    print("      DRUGSHIELD AI - LIVE THREAT PIPELINE        ")
    print("--------------------------------------------------")

    evaluated_records = []
    flagged_threats = 0

    for rec in records:
        if isinstance(rec, dict):
            # Run through active NLP & Threat Flagging Pipeline
            evaluated = evaluate_live_message_threat(rec)
            evaluated_records.append(evaluated)
            if evaluated.get("threat_score", 0.0) >= 0.60 or evaluated.get("flagged_status"):
                flagged_threats += 1

    print(f"Total Intercepted Records Evaluated : {len(evaluated_records)}")
    print(f"Threats Flagged (Score >= 0.60)     : {flagged_threats}")
    print("--------------------------------------------------\n")

    return evaluated_records


def write_to_landing_zone(records):
    init_raw_landing_zone()
    evaluated = process_threat_pipeline(records)
    output_path = RAW_DIR / "ingested_raw_data.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(evaluated, f, indent=4, ensure_ascii=False)

    print("\n==================================================")
    print("      CENTRAL RAW LANDING ZONE STATUS             ")
    print("==================================================")
    print(f"Target Directory   : {RAW_DIR.resolve()}")
    print(f"Ingested JSON File : {output_path.name}")
    print(f"Total Raw Records  : {len(evaluated)}")
    print("==================================================\n")


if __name__ == "__main__":
    init_raw_landing_zone()
    raw_records = asyncio.run(collect_all_crawlers())
    write_to_landing_zone(raw_records)