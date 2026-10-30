"""
DrugShield AI - Module 1 Extension: Smart Buyer Persona Honeypot Bot
===================================================================
Simulates a credible buyer persona to engage suspect vendors once
a thread transitions to ACTIVE_HONEYPOT_READY.

Multi-Stage Conversational Flow:
1. Stage 1 (Initial Engagement on 4-5 flags): Shows interest in buying and EXPLICITLY asks
   for the payment link / UPI QR code.
2. Stage 2 (Suspect sends link / payment details): Bot confirms payment, dispatches the
   decoy transaction invoice link, and asks for the GPS drop coordinates.
3. Stage 3 (Subsequent replies): Maintains two-way conversational loop.
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

# Stage 1: Explicitly state interest in buying AND ask for payment link / UPI QR code
BUYER_PAYMENT_REQUEST_TEMPLATES = [
    "Hey bro, interested in buying. What's the rate for 2g? Send me your payment link or UPI QR code so I can clear the advance.",
    "Bro, I need fresh stock. Ready to pay advance immediately. Please send your UPI ID or payment link.",
    "Bhai quality pure hai na? I am ready to order right now. Send your payment QR or UPI link to transfer advance.",
    "Hey bro, saw your drop menu. I'm interested in buying. Send me the payment link or UPI details so I can transfer the token amount.",
]

# Stage 2: After suspect shares payment link/details -> send confirmation with decoy invoice link
INVOICE_CONFIRMATION_TEMPLATES = [
    "Bro, I've transferred the advance to your payment link. Here is the transaction receipt link: {invoice_url} - send me the drop pin once verified.",
    "Bhai advance token transfer done via UPI! Check the transaction receipt here: {invoice_url} - send the dead drop pin after verifying.",
    "Hey bro, advance payment sent on your link. View the transaction receipt: {invoice_url}. Share the location drop pin once confirmed.",
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
                "stage": "REQUEST_PAYMENT_LINK",  # Initial stage: ask for payment link
            }
        return self.sessions[entity_id]

    def create_tracking_token(self, entity_id: str, platform: str = "simulation") -> str:
        """Generate a random tracking token for the honeypot tracking route."""
        return f"inv_{uuid.uuid4().hex[:12]}"

    def build_invoice_url(self, tracking_token: str) -> str:
        """Construct the URL pointing to the silent IP/fingerprint tracking endpoint."""
        return f"{self.api_base_url}/api/v1/invoice/{tracking_token}"

    def generate_opening_inquiry(self, target_entity: str) -> str:
        """Pick a natural buyer persona opener asking for payment link/QR."""
        return random.choice(BUYER_PAYMENT_REQUEST_TEMPLATES)

    def generate_invoice_dispatch_message(self, invoice_url: str) -> str:
        """Pick an invoice delivery message format."""
        template = random.choice(INVOICE_CONFIRMATION_TEMPLATES)
        return template.format(invoice_url=invoice_url)

    def engage_target(
        self,
        entity_id: str,
        chat_id: str,
        platform: str = "telegram",
        simulation_post_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes the initial honeypot handoff upon reaching 4-5 message threshold:
        1. Transitions entity state to HONEYPOT_ENGAGED.
        2. Dispatches opening buyer message: INTERESTED IN BUYING + ASKS FOR PAYMENT LINK/QR.
        """
        now = datetime.now(timezone.utc).isoformat()
        session = self.get_or_create_session(entity_id, platform)
        session["turn_count"] = 1
        session["stage"] = "REQUEST_PAYMENT_LINK"
        token = session["token"]
        invoice_url = session["invoice_url"]

        # Stage 1 message: Interested in buying + explicitly ask for payment link / UPI QR code
        dispatch_message = self.generate_opening_inquiry(entity_id)

        # Transition to HONEYPOT_ENGAGED
        state_machine.transition_state(
            entity_id=entity_id,
            new_state=STATE_HONEYPOT_ENGAGED,
            reason="Smart Buyer Bot engaged suspect: Inquired buying intent and requested payment link/QR",
            details={"chat_id": chat_id, "platform": platform, "token": token},
        )

        logger.info(f"[Honeypot Bot] Engaged target '{entity_id}' on {platform}. Asked for payment link.")

        return {
            "entity_id": entity_id,
            "chat_id": chat_id,
            "platform": platform,
            "sender_id": "buyer_persona",
            "sender_name": "Rohan",
            "tracking_token": token,
            "invoice_url": invoice_url,
            "dispatched_message": dispatch_message,
            "timestamp": now,
            "turn_count": session["turn_count"],
            "stage": session["stage"],
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
        If suspect provides payment link / QR / UPI details -> send confirmation invoice receipt!
        """
        now = datetime.now(timezone.utc).isoformat()
        session = self.get_or_create_session(entity_id, platform)
        session["turn_count"] += 1
        invoice_url = session["invoice_url"]
        token = session["token"]

        text_lower = (message_text or "").lower()

        # If we were waiting for the payment link/QR, or the dealer sent payment info / qr / upi
        is_payment_info = any(w in text_lower for w in [
            "upi", "paytm", "gpay", "phonepe", "@", "link", "qr", "qr code", "advance", "token", "scan", "send here", "pay"
        ])

        if session.get("stage") == "REQUEST_PAYMENT_LINK" or is_payment_info:
            # Advance to Stage 2: Send payment confirmation receipt link!
            session["stage"] = "INVOICE_SENT"
            reply_text = self.generate_invoice_dispatch_message(invoice_url)

            state_machine.transition_state(
                entity_id=entity_id,
                new_state=STATE_INVOICE_SENT,
                reason=f"Tracking invoice link dispatched following dealer payment reply: {invoice_url}",
                details={"tracking_token": token, "invoice_url": invoice_url},
            )
        elif any(w in text_lower for w in ["screenshot", "ss", "proof", "receipt", "slip", "payment", "aaya", "bheja", "check"]):
            template = random.choice(REPLY_TEMPLATES_PROOF)
            reply_text = template.format(invoice_url=invoice_url)
        elif any(w in text_lower for w in ["drop", "pin", "location", "address", "kaha", "where", "gps", "coordinates", "pickup", "point"]):
            reply_text = random.choice(REPLY_TEMPLATES_LOCATION)
        elif any(w in text_lower for w in ["rate", "price", "cash", "more", "extra", "balance", "paise", "rupaye"]):
            template = random.choice(REPLY_TEMPLATES_PAYMENT)
            reply_text = template.format(invoice_url=invoice_url)
        elif any(w in text_lower for w in ["ok", "okay", "wait", "hold", "1 min", "dekhta", "checking", "haan"]):
            reply_text = random.choice(REPLY_TEMPLATES_CONFIRMATION)
        else:
            template = random.choice(REPLY_TEMPLATES_DEFAULT)
            reply_text = template.format(invoice_url=invoice_url)

        logger.info(f"[Honeypot Bot Reply] To '{entity_id}' on {platform}: {reply_text}")

        return {
            "entity_id": entity_id,
            "chat_id": chat_id,
            "platform": platform,
            "sender_id": "buyer_persona",
            "sender_name": "Rohan",
            "tracking_token": token,
            "invoice_url": invoice_url,
            "dispatched_message": reply_text,
            "timestamp": now,
            "turn_count": session["turn_count"],
            "stage": session.get("stage", "ACTIVE"),
        }


buyer_bot = SmartBuyerBot()
