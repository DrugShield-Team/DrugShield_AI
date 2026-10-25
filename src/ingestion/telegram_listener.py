"""
DrugShield AI - Telegram Listener Integration Entrypoint
=========================================================
Wraps telegram_telegram.py to process live real-time message streams.
Eliminates static mock JSON data and feeds live frames into the threat pipeline.
"""

import sys
import asyncio
from pathlib import Path

FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent.parent
PROJECT_ROOT = SRC_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.telegram_telegram import (
    TelegramPassiveCrawler,
    run_telegram_crawler,
    run_telegram_crawler_async
)

async def run_telegram_crawler_pipeline():
    """Pipeline caller from main.py."""
    return await run_telegram_crawler_async()

def run():
    return asyncio.run(run_telegram_crawler_pipeline())

if __name__ == "__main__":
    run_telegram_crawler()