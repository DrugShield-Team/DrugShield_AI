# src/ingestion/telegram_listener.py

import os
import json
import asyncio
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from datetime import datetime

# Make local package imports resolvable when the module is run directly or via VS Code.
for candidate in (Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[2]):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

try:
    from telethon import TelegramClient, events  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    class TelegramClient:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self._error = RuntimeError(
                "The 'telethon' package is required for Telegram ingestion. Install it with `pip install telethon`."
            )

        def on(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        async def start(self):
            raise self._error

        async def run_until_disconnected(self):
            raise self._error

    class _EventsStub:
        @staticmethod
        def NewMessage(*args, **kwargs):
            return object()

    events = _EventsStub()

try:
    from config.settings import (
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
        TELEGRAM_SESSION_NAME,
        RAW_DATA_DIR,
        RAW_IMAGES_DIR,
    )
except ImportError:  # pragma: no cover - fallback for direct execution / VS Code analysis
    settings_path = None
    for base_dir in (
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve().parents[2],
    ):
        candidate = base_dir / "config" / "settings.py"
        if candidate.exists():
            settings_path = candidate
            break

    if settings_path is None:
        raise

    settings_spec = spec_from_file_location("config.settings", settings_path)
    if settings_spec is None or settings_spec.loader is None:
        raise ImportError(f"Unable to load settings from {settings_path}")

    settings_module = module_from_spec(settings_spec)
    settings_spec.loader.exec_module(settings_module)

    TELEGRAM_API_ID = settings_module.TELEGRAM_API_ID
    TELEGRAM_API_HASH = settings_module.TELEGRAM_API_HASH
    TELEGRAM_SESSION_NAME = settings_module.TELEGRAM_SESSION_NAME
    RAW_DATA_DIR = settings_module.RAW_DATA_DIR
    RAW_IMAGES_DIR = settings_module.RAW_IMAGES_DIR

# Target Telegram channels or public groups to monitor
TARGET_CHANNELS = [
    'blr_test_supplies',  # Replace with public test channel usernames or IDs
]

# Initialize Telethon Client using MTProto Protocol
if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
    raise ValueError("TELEGRAM_API_ID or TELEGRAM_API_HASH missing in .env file.")

client = TelegramClient(TELEGRAM_SESSION_NAME, int(TELEGRAM_API_ID), TELEGRAM_API_HASH)

async def parse_and_store_message(event):
    """
    Extracts text and metadata from an incoming message, saves media locally,
    and constructs a standardized JSON payload for downstream pipeline processing.
    """
    sender = await event.get_sender()
    sender_id = str(sender.id) if sender else "Unknown"
    sender_username = getattr(sender, 'username', 'N/A')
    chat_title = event.chat.title if event.chat else "Private/Direct Chat"
    
    text = event.message.text or ""
    media_filepath = None

    # Download attached image/photo if available (e.g., drug menu card or QR)
    if event.message.photo or event.message.media:
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"tg_{event.message.id}_{timestamp_str}.jpg"
        target_path = os.path.join(RAW_IMAGES_DIR, file_name)
        
        # Download media asynchronously
        media_filepath = await event.message.download_media(file=target_path)

    # Standardized Payload Schema
    payload = {
        "platform": "telegram",
        "chat_title": chat_title,
        "message_id": event.message.id,
        "sender_id": sender_id,
        "sender_handle": f"@{sender_username}" if sender_username else "N/A",
        "text_content": text,
        "media_path": media_filepath,
        "timestamp": event.message.date.isoformat() if event.message.date else datetime.now().isoformat()
    }

    print(f"\n[+] [TELEGRAM INGESTED] {datetime.now().strftime('%H:%M:%S')}")
    print(f"    ├─ Channel: {chat_title}")
    print(f"    ├─ Handle: {payload['sender_handle']}")
    print(f"    ├─ Text Snippet: {text[:60]}..." if text else "    ├─ Text Snippet: [Image/Media Only]")
    if media_filepath:
        print(f"    └─ Media Saved: {media_filepath}")

    # Save to raw JSON log folder for file-based pipeline fallback
    log_file = os.path.join(RAW_DATA_DIR, f"tg_log_{event.message.id}.json")
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)

    return payload


# 1. Real-Time Event Listener
@client.on(events.NewMessage(chats=TARGET_CHANNELS))
async def live_message_event_handler(event):
    """Triggers immediately when a new message is posted in monitored channels."""
    await parse_and_store_message(event)


# 2. Historical Scraper / Backfill Worker
async def scrape_historical_messages(channel_name: str, limit: int = 50):
    """
    Crawls past messages from a target public channel.
    Useful for initializing intelligence graphs prior to live monitoring.
    """
    print(f"[*] Crawling last {limit} historical posts from @{channel_name}...")
    async for message in client.iter_messages(channel_name, limit=limit):
        text = message.text or ""
        print(f"    └─ Historical Post [{message.id}]: {text[:40]}...")


async def start_telegram_ingestion():
    """Main execution entry point for the Telegram Service."""
    print("[*] Launching DrugShield AI - Telegram Ingestion Engine...")
    await client.start()
    print("[+] Connection Established via MTProto API.")
    print(f"[*] Monitoring Active Targets: {TARGET_CHANNELS}")
    
    # Run loop indefinitely until service is stopped
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(start_telegram_ingestion())
    except KeyboardInterrupt:
        print("\n[-] Telegram Ingestion Engine stopped by user.")