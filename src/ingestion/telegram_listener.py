import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Project paths
FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent
PROJECT_ROOT = SRC_DIR.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
RAW_IMAGES_DIR = RAW_DATA_DIR / "images"

# Fetch Telegram Credentials
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "anon")

TARGET_CHANNELS = ['blr_test_supplies']

def get_telegram_fallback_data():
    """Generates fallback records when live API is unavailable."""
    return [
        {
            "platform": "telegram",
            "chat_title": "BLR Party Supplies",
            "message_id": 991,
            "sender_id": "1002345",
            "sender_handle": "@blr_supplies_bot",
            "text_content": "Fresh stock MDMA 1g 3k. Fast delivery in Bengaluru. DM @blr_supplies_bot UPI dealer@ybl",
            "media_path": str(RAW_IMAGES_DIR / "tg_991_demo.jpg"),
            "timestamp": datetime.now().isoformat(),
            "is_fallback_mock": True
        }
    ]

async def run_telegram_crawler():
    """Primary pipeline entry point called by main.py."""
    print("\n==================================================")
    print("      DRUGSHIELD AI - TELEGRAM INGESTION ENGINE   ")
    print("==================================================")
    
    # Check credentials
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH or TELEGRAM_API_HASH == "dummy_hash_for_testing":
        print("[*] Telegram: Credentials unconfigured or set to test placeholder. Using Mock Fallback...")
        return get_telegram_fallback_data()

    try:
        from telethon import TelegramClient
        client = TelegramClient(TELEGRAM_SESSION_NAME, int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            print("[*] Telegram: Client session unauthorized. Using Mock Fallback...")
            await client.disconnect()
            return get_telegram_fallback_data()

        print(f"[*] Telegram: Crawling messages from {TARGET_CHANNELS}...")
        results = []
        for channel in TARGET_CHANNELS:
            async for message in client.iter_messages(channel, limit=5):
                results.append({
                    "platform": "telegram",
                    "chat_title": channel,
                    "message_id": message.id,
                    "sender_handle": "@" + (getattr(message.sender, 'username', None) or "N/A"),
                    "text_content": message.text or "",
                    "timestamp": message.date.isoformat() if message.date else datetime.now().isoformat(),
                    "is_fallback_mock": False
                })
        await client.disconnect()
        return results if results else get_telegram_fallback_data()
        
    except Exception as e:
        print(f"[Telegram Notice] Operating in fallback mode: {e}")
        return get_telegram_fallback_data()

def run():
    return asyncio.run(run_telegram_crawler())