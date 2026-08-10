import json
import random
import os
from datetime import datetime, timedelta

def generate_whatsapp_mock_data(count=5, output_file="whatsapp_simulated.json"):
    """
    Generates synthetic WhatsApp chat solicitation data containing drug slang,
    UPI VPAs, and media paths for offline testing and viva demonstrations.
    """
    
    # 1. Target keyword, emoji, and entity pools matching DrugShield AI specs
    senders = [
        {"name": "Phantom_NCR", "phone": "+91 98765 43210"},
        {"name": "Delhi_Score_Bot", "phone": "+91 91234 56789"},
        {"name": "Vibe_Dealer_Gurgaon", "phone": "+91 99887 76655"},
        {"name": "Stamps_Direct", "phone": "+91 95554 33211"},
        {"name": "Anon_Delivery_01", "phone": "+91 90000 11223"}
    ]

    chat_titles = [
        "NCR Private Party Supplies 🍃",
        "Delhi Score & Chill",
        "Gurgaon Underground Network",
        "Fast Delivery NCR/Noida",
        "Public Menu Hub"
    ]

    solicitation_templates = [
        "Fresh Mal 🍃 and Molly 💊 ready in South Delhi. Rate list in menu card. Pay via UPI: {vpa}",
        "Top quality LSD Stamps 🪪 and Chitta available. DM for drop location. UPI ID: {vpa}",
        "Mephedrone (❄️) score clear. Pure material guaranteed. Send token amount on {vpa} to get GPS pin.",
        "Ganja 🍃 100g packs ready. Fast deal near Metro Station. UPI payment only: {vpa}",
        "MDMA 💊 and Stamp 🪪 stock refreshed. Check menu image attached. UPI handle: {vpa}"
    ]

    upi_vpas = [
        "fastpay99@okaxis",
        "score_vendor@ybl",
        "dark_supply@paytm",
        "ncr_plug@upi",
        "token_receiver@icici"
    ]

    sample_media = [
        "downloads/menu_card_01.jpg",
        "downloads/qr_code_02.png",
        "downloads/price_list_03.jpg",
        None
    ]

    mock_entries = []
    base_time = datetime.now()

    # 2. Construct mock records
    for i in range(count):
        sender = random.choice(senders)
        selected_vpa = random.choice(upi_vpas)
        media_path = random.choice(sample_media)
        timestamp = (base_time - timedelta(minutes=random.randint(2, 120))).isoformat()

        entry = {
            "entry_id": f"WA_MOCK_{i+1:03d}",
            "timestamp": timestamp,
            "platform": "WhatsApp",
            "chat_id": f"{sender['phone'].replace('+', '').replace(' ', '')}@c.us",
            "chat_title": random.choice(chat_titles),
            "sender_id": sender["phone"],
            "sender_username": sender["name"],
            "message_text": random.choice(solicitation_templates).format(vpa=selected_vpa),
            "has_media": media_path is not None,
            "media_path": media_path,
            "extracted_vpa": selected_vpa,
            "processed_by_ai": False
        }
        mock_entries.append(entry)

    # 3. Save generated payload to local JSON file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(mock_entries, f, indent=4, ensure_ascii=False)

    print(f"[+] Successfully generated {count} simulated records -> '{output_file}'")

if __name__ == "__main__":
    # Ensure download directory exists to simulate media targets
    os.makedirs("downloads", exist_ok=True)
    generate_whatsapp_mock_data(count=6, output_file="whatsapp_simulated.json")