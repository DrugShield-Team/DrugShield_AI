"""
DrugShield AI - WhatsApp Feed Ingestion Controller
File Location: src/ingestion/whatsapp_feed.py

Description:
Manages the ingestion pipeline for WhatsApp data. Supports both live 
public group link inspection (via BeautifulSoup) and offline mock generation 
for viva demonstrations.
"""

import os
import json
import time
import random
from pathlib import Path

# Import mock generator and live link inspector safely
try:
    from .watsapp_mock_generator import generate_whatsapp_mock_data
    from .whatsapp_link_inspector import inspect_whatsapp_link
except ImportError:
    # Fallback for direct execution in directory
    from watsapp_mock_generator import generate_whatsapp_mock_data
    from whatsapp_link_inspector import inspect_whatsapp_link

# Path Resolution
FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent
PROJECT_ROOT = SRC_DIR.parent
MOCK_FILE_PATH = PROJECT_ROOT / "whatsapp_simulated.json"
MASTER_DATA_FILE = PROJECT_ROOT / "data.json"

def load_and_append_to_master(records: list):
    """Appends collected records to master data.json file for the AI pipeline."""
    if not records:
        return

    if os.path.exists(MASTER_DATA_FILE):
        with open(MASTER_DATA_FILE, "r", encoding="utf-8") as f:
            try:
                master_data = json.load(f)
            except json.JSONDecodeError:
                master_data = []
    else:
        master_data = []

    master_data.extend(records)

    with open(MASTER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(master_data, f, indent=4, ensure_ascii=False)

    print(f"[+] Successfully integrated {len(records)} WhatsApp records into '{MASTER_DATA_FILE}'")

def scrape_whatsapp_feed(use_mock: bool = True, live_invite_urls: list = None, limit: int = 5):
    """
    Primary ingestion controller for WhatsApp.
    - If use_mock=True: Loads simulated records for safe offline testing.
    - If use_mock=False: Scrapes real public group preview metadata using live invite URLs.
    """
    collected_records = []

    if use_mock:
        print("[*] WhatsApp Ingestion: Running in MOCK MODE (Offline Safety Fallback)...")
        time.sleep(random.uniform(0.3, 0.8))  # Execution delay simulation
        
        if not os.path.exists(MOCK_FILE_PATH):
            generate_whatsapp_mock_data(count=6, output_file=str(MOCK_FILE_PATH))

        with open(MOCK_FILE_PATH, "r", encoding="utf-8") as f:
            try:
                collected_records = json.load(f)
            except json.JSONDecodeError:
                collected_records = []
    else:
        print("[*] WhatsApp Ingestion: Running in LIVE OSINT MODE...")
        if not live_invite_urls:
            print("[-] No live invite URLs provided for scanning.")
            return []

        for url in live_invite_urls:
            result = inspect_whatsapp_link(url)
            if result:
                collected_records.append(result)
            time.sleep(1) # Polite scraping delay

    # Save all gathered records into the master pipeline file
    load_and_append_to_master(collected_records)
    return collected_records[:limit]

if __name__ == "__main__":
    # --- DEMO 1: Run in Mock Mode (Great for Viva / No Internet) ---
    print("=" * 60)
    print("      SCENARIO A: WHATSAPP MOCK FEED INGESTION           ")
    print("=" * 60)
    chats = scrape_whatsapp_feed(use_mock=True)
    
    print("\n[✔] DISPLAYING PROCESSED MOCK WHATSAPP FEED:")
    for idx, item in enumerate(chats, start=1):
        print(f"[{idx}] Source: {item.get('sender_username')} ({item.get('sender_id')})")
        print(f"    Chat Title: {item.get('chat_title')}")
        print(f"    Message: {item.get('message_text')}")
        print(f"    Extracted UPI VPA: {item.get('extracted_vpa')}\n")

    # --- DEMO 2: Run in Live Mode (Active OSINT Inspection) ---
    print("=" * 60)
    print("      SCENARIO B: LIVE PUBLIC LINK OSINT INSPECTION    ")
    print("=" * 60)
    
    # Replace with an actual public group invite link if available, or test with a public link
    sample_public_links = [
        "https://chat.whatsapp.com/J12345ExampleCode1", 
    ]
    
    live_chats = scrape_whatsapp_feed(use_mock=False, live_invite_urls=sample_public_links)
    
    if live_chats:
        print("\n[✔] DISPLAYING LIVE SCRAPED WHATSAPP DATA:")
        for idx, item in enumerate(live_chats, start=1):
            print(f"[{idx}] Group Title: {item.get('chat_title')}")
            print(f"    Invite URL: {item.get('invite_url')}")
            print(f"    Description: {item.get('group_description')}")
            print(f"    Extracted UPI VPA: {item.get('extracted_vpa')}\n")
    else:
        print("\n[-] No live chats collected or link expired/invalid.")