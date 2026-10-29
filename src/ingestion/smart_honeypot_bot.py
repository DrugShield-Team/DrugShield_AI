"""
DrugShield AI - Module 1 Extension: Smart Buyer Persona Honeypot Bot
===================================================================
Simulates a credible buyer persona to engage suspect vendors once
a thread transitions to ACTIVE_HONEYPOT_READY. Solicits pricing and
delivery pins, and dispatches an authentic-looking payment verification /
invoice link embedded with passive OSINT tracking hooks.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

from src.cases.state_machine import (
    STATE_HONEYPOT_ENGAGED,
    STATE_INVOICE_SENT,
    state_machine,
)

logger = logging.getLogger("DrugShield.SmartBuyerBot")

# Natural buyer inquiry templates in Hinglish & English (undercover customer persona)
BUYER_ENGAGEMENT_TEMPLATES = [
    "Hey bro, interested in buying. What's the rate for 2g? Where will you drop the location pin?",
    "Bro, need fresh stock. Can pay advance token immediately via UPI. Send payment link or details.",
    "Bhai quality pure hai na? Send me payment details or invoice link, I'll clear the advance right away.",
    "Hey bro, saw your drop menu. Ready to lock the order. Send payment link or receipt so I can verify and get the drop pin.",
]

# Invoice receipt presentation templates (natural customer confirming a transaction)
INVOICE_DISPATCH_TEMPLATES = [
    "Bro, I've transferred the advance to your UPI ID. Here is the transaction receipt link: {invoice_url} - send me the drop pin once verified.",
    "Bhai advance token transfer done via UPI! Check the transaction receipt here: {invoice_url} - send the dead drop pin after verifying.",
    "Hey bro, advance payment sent. View the transaction receipt link: {invoice_url}. Share the location drop pin once confirmed.",
    "Payment complete bro! UPI transaction receipt link: {invoice_url} - please check and send the GPS drop coordinates.",
]

# Contextual reply templates for two-way dynamic conversational loop
REPLY_TEMPLATES_PROOF = [
    "Bhai screenshot link me clear dikh raha hai: {invoice_url} - instant UPI clearing reference hai, check kar lo.",
    "Bhai payment account se cut chuka hai! Transaction copy yaha verify karo: {invoice_url} - dekh kar confirm karo.",
    "Bro, payment confirmation slip is attached right here: {invoice_url}. Check and send drop pin.",
]

REPLY_TEMPLATES_LOCATION = [
    "Bhai main nearby hi wait kar raha hu, jaldi GPS drop pin share karo taaki main safely pickup kar saku.",
    "Receipt verify kar li na bhai? Exact dead drop coordinates pin bhej do, I'll pick it up immediately.",
    "Haan bhai South Delhi route pe hi hu, send the exact GPS pin so I can reach.",
]

REPLY_TEMPLATES_PAYMENT = [
    "Bhai INR 3,500 token advance to transfer kar diya receipt link mein: {invoice_url}. Baaki balance pickup ke time cash de dunga.",
    "Advance token transfer locked hai bro. Pehle drop pin bhejo verify karke, tabhi safe rahega.",
]

REPLY_TEMPLATES_CONFIRMATION = [
    "Theek hai bhai, jaldi check kar ke GPS drop pin bhejo, waiting here.",
    "Sure bro, jaldi confirm karo so we can lock the delivery.",
]

REPLY_TEMPLATES_DEFAULT = [
    "Haan bhai, payment ho chuka hai. Receipt link verify kar lo: {invoice_url} - aur final drop pin coordinate bhej do please.",
    "Bro advance is settled. Just waiting for your drop location pin so I can pick up.",
    "Bhai slip link verify karke drop pin send karo: {invoice_url}. Need it urgently.",
]


class SmartBuyerBot:
    """
    Simulates automated buyer persona engagement for honeypot operations.
    Maintains dynamic two-way conversation state across multiple chat turns.
    """

    def __init__(self, api_base_url: str = "http://127.0.0.1:8000"):
        self.api_base_url = api_base_url.rstrip("/")
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create_session(self, entity_id: str, platform: str = "whatsapp") -> Dict[str, Any]:
        """Retrieve existing tracked session or initialize a fresh one."""
        if entity_id not in self.sessions:
            token = self.create_tracking_token(entity_id, platform)
            invoice_url = self.build_invoice_url(token)
            self.sessions[entity_id] = {
                "token": token,
                "invoice_url": invoice_url,
                "platform": platform,
                "turn_count": 0,
            }
        return self.sessions[entity_id]

    def create_tracking_token(self, entity_id: str, platform: str = "simulation") -> str:
        """Generate a random tracking token for the honeypot tracking route."""
        return f"inv_{uuid.uuid4().hex[:12]}"

    def build_invoice_url(self, tracking_token: str) -> str:
        """Construct the URL pointing to the silent IP/fingerprint tracking endpoint."""
        return f"{self.api_base_url}/api/v1/invoice/{tracking_token}"

    def generate_opening_inquiry(self, target_entity: str) -> str:
        """Pick a natural buyer persona opener."""
        return random.choice(BUYER_ENGAGEMENT_TEMPLATES)

    def generate_invoice_dispatch_message(self, invoice_url: str) -> str:
        """Pick an invoice delivery message format."""
        template = random.choice(INVOICE_DISPATCH_TEMPLATES)
        return template.format(invoice_url=invoice_url)

    def engage_target(
        self,
        entity_id: str,
        chat_id: str,
        platform: str = "telegram",
        simulation_post_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes the initial honeypot handoff:
        1. Transitions entity state to HONEYPOT_ENGAGED.
        2. Generates tracking token and invoice link.
        3. Constructs buyer persona message.
        4. Transitions entity state to INVOICE_SENT.
        5. Attempts to dispatch to the local simulation endpoint if available.
        """
        now = datetime.now(timezone.utc).isoformat()
        session = self.get_or_create_session(entity_id, platform)
        session["turn_count"] = 1
        token = session["token"]
        invoice_url = session["invoice_url"]
        dispatch_message = self.generate_invoice_dispatch_message(invoice_url)

        # 1. Transition to HONEYPOT_ENGAGED
        state_machine.transition_state(
            entity_id=entity_id,
            new_state=STATE_HONEYPOT_ENGAGED,
            reason="Smart Buyer Bot initiated automated engagement sequence",
            details={"chat_id": chat_id, "platform": platform, "token": token},
        )

        # 2. Advance to INVOICE_SENT
        state_machine.transition_state(
            entity_id=entity_id,
            new_state=STATE_INVOICE_SENT,
            reason=f"Tracking invoice link dispatched: {invoice_url}",
            details={"tracking_token": token, "invoice_url": invoice_url},
        )

        dispatched_to_network = False
        target_endpoint = simulation_post_url
        if not target_endpoint:
            if platform == "telegram":
                target_endpoint = "http://localhost:8000/api/send"
            elif platform == "whatsapp":
                target_endpoint = "http://localhost:8090/api/send"

        if target_endpoint:
            try:
                payload = {
                    "chat_id": chat_id,
                    "sender_id": "buyer_persona",
                    "sender_name": "Rohan",
                    "message": dispatch_message,
                    "timestamp": now,
                }
                resp = requests.post(target_endpoint, json=payload, timeout=1.0)
                if resp.status_code in (200, 201):
                    dispatched_to_network = True
            except Exception:
                # Simulation server might be offline during headless testing
                pass

        logger.info(f"[Honeypot Bot] Engaged target '{entity_id}' on {platform}. Invoice: {invoice_url}")

        return {
            "entity_id": entity_id,
            "chat_id": chat_id,
            "platform": platform,
            "sender_id": "buyer_persona",
            "sender_name": "Rohan",
            "tracking_token": token,
            "invoice_url": invoice_url,
            "dispatched_message": dispatch_message,
            "dispatched_to_network": dispatched_to_network,
            "timestamp": now,
            "turn_count": session["turn_count"],
        }

    def handle_target_reply(
        self,
        entity_id: str,
        chat_id: str,
        message_text: str,
        platform: str = "whatsapp",
        simulation_post_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Maintains two-way conversational loop once honeypot is engaged.
        Analyzes the target/seller's message and returns contextual follow-up.
        """
        now = datetime.now(timezone.utc).isoformat()
        session = self.get_or_create_session(entity_id, platform)
        session["turn_count"] += 1
        invoice_url = session["invoice_url"]
        token = session["token"]

        text_lower = (message_text or "").lower()

        # Keyword-based contextual intent routing
        if any(w in text_lower for w in ["screenshot", "ss", "proof", "receipt", "slip", "payment", "aaya", "bheja", "paytm", "upi", "check"]):
            template = random.choice(REPLY_TEMPLATES_PROOF)
        elif any(w in text_lower for w in ["drop", "pin", "location", "address", "kaha", "where", "gps", "coordinates", "pickup", "point"]):
            template = random.choice(REPLY_TEMPLATES_LOCATION)
        elif any(w in text_lower for w in ["rate", "price", "cash", "more", "extra", "balance", "paise", "rupaye", "discount"]):
            template = random.choice(REPLY_TEMPLATES_PAYMENT)
        elif any(w in text_lower for w in ["ok", "okay", "wait", "hold", "1 min", "dekhta", "checking", "haan", "bol"]):
            template = random.choice(REPLY_TEMPLATES_CONFIRMATION)
        else:
            template = random.choice(REPLY_TEMPLATES_DEFAULT)

        reply_message = template.format(invoice_url=invoice_url)

        # Dispatch via simulation server webhook if online
        dispatched_to_network = False
        target_endpoint = simulation_post_url
        if not target_endpoint:
            if platform == "telegram":
                target_endpoint = "http://localhost:8000/api/send"
            elif platform == "whatsapp":
                target_endpoint = "http://localhost:8090/api/send"

        if target_endpoint:
            try:
                payload = {
                    "chat_id": chat_id,
                    "sender_id": "buyer_persona",
                    "sender_name": "Rohan",
                    "message": reply_message,
                    "timestamp": now,
                }
                resp = requests.post(target_endpoint, json=payload, timeout=1.0)
                if resp.status_code in (200, 201):
                    dispatched_to_network = True
            except Exception:
                pass

        logger.info(f"[Honeypot Bot Conversational Loop] Entity: {entity_id} (Turn {session['turn_count']}) | Reply: {reply_message}")

        return {
            "entity_id": entity_id,
            "chat_id": chat_id,
            "platform": platform,
            "sender_id": "buyer_persona",
            "sender_name": "Rohan",
            "tracking_token": token,
            "invoice_url": invoice_url,
            "dispatched_message": reply_message,
            "dispatched_to_network": dispatched_to_network,
            "timestamp": now,
            "is_followup": True,
            "turn_count": session["turn_count"],
        }


# Global singleton
buyer_bot = SmartBuyerBot()
