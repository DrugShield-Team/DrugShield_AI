"""
DrugShield AI - WhatsApp Link Inspector Module
File Location: src/ingestion/whatsapp_link_inspector.py

Description:
Scrapes public metadata from a WhatsApp group invite link (chat.whatsapp.com/...)
without joining the group or requiring WhatsApp login, utilizing OpenGraph tags.
"""

import re
import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

# Path Resolution
FILE_PATH = Path(__file__).resolve()
SRC_DIR = FILE_PATH.parent.parent
PROJECT_ROOT = SRC_DIR.parent
DATA_FILE = PROJECT_ROOT / "data.json"

def inspect_whatsapp_link(invite_url: str) -> dict | None:
    """
    Scrapes public metadata from a WhatsApp group invite link 
    without joining the group or requiring WhatsApp login.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    try:
        print(f"[*] Inspecting live public WhatsApp link: {invite_url}")
        response = requests.get(invite_url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"[-] Failed to fetch link. Status code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        # OpenGraph meta tags contain public preview data
        og_title = soup.find("meta", property="og:title")
        og_description = soup.find("meta", property="og:description")
        og_image = soup.find("meta", property="og:image")

        group_title = og_title["content"] if og_title else "Unknown Group"
        group_desc = og_description["content"] if og_description else ""
        group_icon = og_image["content"] if og_image else ""

        # Extract potential phone numbers or UPI handles embedded in description text
        upi_matches = re.findall(r'[a-zA-Z0-9.\-_]+@[a-zA-Z]+', group_desc)
        phone_matches = re.findall(r'\+?\d{10,12}', group_desc)

        payload = {
            "entry_id": f"WA_LIVE_{datetime.now().strftime('%H%M%S%f')}",
            "timestamp": datetime.now().isoformat(),
            "platform": "WhatsApp",
            "source_type": "Public Invite Link",
            "invite_url": invite_url,
            "chat_title": group_title,
            "group_description": group_desc,
            "group_icon_url": group_icon,
            "sender_id": phone_matches[0] if phone_matches else "Unknown_Sender",
            "sender_username": group_title,
            "message_text": group_desc,
            "extracted_vpa": upi_matches[0] if upi_matches else None,
            "extracted_phones": phone_matches,
            "processed_by_ai": False
        }

        # Save to common data repository
        save_to_data_json(payload)
        print(f"[+] Successfully scraped metadata for live group: '{group_title}'")
        return payload

    except Exception as e:
        print(f"[-] Error inspecting WhatsApp link: {e}")
        return None

def save_to_data_json(payload: dict):
    """Appends payload to master data.json file."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    data.append(payload)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    # Test link execution
    sample_invite = "https://chat.whatsapp.com/ExampaleGroupInviteCode123"
    inspect_whatsapp_link(sample_invite)