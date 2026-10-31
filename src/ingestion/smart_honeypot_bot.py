"""
DrugShield AI - Module 1 Extension: Smart Buyer Persona Honeypot Bot
===================================================================
Simulates a credible buyer persona to engage suspect vendors once
a thread transitions to ACTIVE_HONEYPOT_READY.

Multi-Stage Conversational Flow:
1. Stage 1 (Initial Engagement on 4-5 flags): Shows interest in buying and EXPLICITLY asks
   for the payment link / UPI QR code.
2. Stage 2 (Suspect sends link / payment details or illicit terms): Bot confirms payment,
   dispatches the decoy escrow transaction invoice link after designated delay, and asks
   for the GPS drop coordinates.
3. Stage 3 (Subsequent replies): Maintains two-way conversational loop.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests
import time

from src.cases.state_machine import (
    STATE_ACTIVE_HONEYPOT_READY,
    STATE_PASSIVE_MONITOR,
    STATE_HONEYPOT_ENGAGED,
    STATE_INVOICE_SENT,
    STATE_TARGET_GEO_LOCATED,
    STATE_DISPATCH_INITIATED,
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

# Stage 2A: Initial payment confirmation prompt before sending payload receipt link
INITIAL_PAYMENT_CONFIRMATION_TEMPLATES = [
    "Transfer initiated on your payment handle! Processing transaction confirmation...",
    "Done bro, payment initiated on your link! Fetching gateway confirmation slip...",
    "Bhai payment transfer initiate kar diya hai. Ek second receipt nikal raha hu...",
    "Advance transfer initiated on your details. Waiting for gateway receipt confirmation...",
]

# Stage 2B: After suspect shares payment link/details -> send confirmation with decoy invoice link
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

    def __init__(self, api_base_url: str = "http://127.0.0.1:8000", sequence_delay_seconds: float = 5.0):
        self.api_base_url = api_base_url.rstrip("/")
        self.sequence_delay_seconds = sequence_delay_seconds
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
                "stage": "REQUEST_PAYMENT_LINK",
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

    def generate_initial_payment_confirmation(self) -> str:
        """Pick an initial payment confirmation prompt before sending payload receipt link."""
        return random.choice(INITIAL_PAYMENT_CONFIRMATION_TEMPLATES)

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
        message_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes the initial honeypot handoff upon reaching 4-5 message threshold:
        1. Transitions entity state to HONEYPOT_ENGAGED / INVOICE_SENT.
        2. Dispatches opening buyer message sequence with escrow payment link sequence.
        """
        now = datetime.now(timezone.utc).isoformat()
        session = self.get_or_create_session(entity_id, platform)
        session["turn_count"] = 1
        session["stage"] = "INVOICE_SENT"
        token = session["token"]
        invoice_url = session["invoice_url"]

        initial_prompt = self.generate_initial_payment_confirmation()
        dispatch_message = self.generate_invoice_dispatch_message(invoice_url)

        # Transition to INVOICE_SENT
        state_machine.transition_state(
            entity_id=entity_id,
            new_state=STATE_INVOICE_SENT,
            reason="Smart Buyer Bot engaged suspect: Inquired buying intent and initiated escrow payment sequence",
            details={"chat_id": chat_id, "platform": platform, "token": token, "invoice_url": invoice_url},
        )

        logger.info(f"[Honeypot Bot] Engaged target '{entity_id}' on {platform}. Escrow sequence initiated.")

        return {
            "entity_id": entity_id,
            "chat_id": chat_id,
            "platform": platform,
            "sender_id": "buyer_persona",
            "sender_name": "Rohan",
            "tracking_token": token,
            "invoice_url": invoice_url,
            "initial_confirmation_prompt": initial_prompt,
            "dispatched_message": dispatch_message,
            "delay_seconds": self.sequence_delay_seconds,
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
        delay_seconds: Optional[float] = None,
        block_thread: bool = False,
    ) -> Dict[str, Any]:
        """
        Maintains two-way conversational loop once honeypot is engaged.
        If suspect provides payment link / QR / UPI details or drug terms:
        1. Sends initial payment confirmation prompt.
        2. Returns designated delay (5.0s) for non-blocking UI delivery.
        3. Dispatches final follow-up phishing / payload link.
        """
        now = datetime.now(timezone.utc).isoformat()
        session = self.get_or_create_session(entity_id, platform)
        session["turn_count"] += 1
        invoice_url = session["invoice_url"]
        token = session["token"]

        text_lower = (message_text or "").lower()

        # Check for payment or illicit deal terms
        is_payment_or_deal_info = any(w in text_lower for w in [
            "upi", "paytm", "gpay", "phonepe", "@", "link", "qr", "qr code", "advance",
            "token", "scan", "send here", "pay", "rate", "price", "rupee", "inr",
            "weed", "coke", "mdma", "chitta", "hash", "lsd", "stamps", "pills", "stuff",
            "m-cat", "ganja", "charas", "cocaine", "ice", "meth", "ketamine", "score",
            "malana", "gram", "2g", "5g", "10g", "stock", "pure", "quality"
        ])

        initial_prompt = None
        delay_to_apply = delay_seconds if delay_seconds is not None else self.sequence_delay_seconds

        if session.get("stage") in ("REQUEST_PAYMENT_LINK", "INVOICE_SENT") or is_payment_or_deal_info:
            session["stage"] = "INVOICE_SENT"
            initial_prompt = self.generate_initial_payment_confirmation()
            logger.info(f"[Honeypot Bot Initial Confirmation] To '{entity_id}' on {platform}: {initial_prompt}")

            if simulation_post_url:
                try:
                    requests.post(
                        simulation_post_url,
                        json={
                            "chat_id": chat_id,
                            "sender_id": "buyer_persona",
                            "sender_name": "Rohan",
                            "text": initial_prompt,
                            "is_analyst": True,
                        },
                        timeout=1.0
                    )
                except Exception as exc:
                    logger.debug(f"Could not post initial prompt to simulation URL: {exc}")

            if block_thread and delay_to_apply > 0:
                time.sleep(delay_to_apply)

            reply_text = self.generate_invoice_dispatch_message(invoice_url)

            state_machine.transition_state(
                entity_id=entity_id,
                new_state=STATE_INVOICE_SENT,
                reason=f"Tracking invoice link dispatched following dealer payment reply: {invoice_url}",
                details={"tracking_token": token, "invoice_url": invoice_url, "initial_prompt": initial_prompt},
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
            "initial_confirmation_prompt": initial_prompt,
            "dispatched_message": reply_text,
            "followup_message": reply_text,
            "delay_seconds": delay_to_apply,
            "timestamp": now,
            "turn_count": session["turn_count"],
            "stage": session.get("stage", "ACTIVE"),
        }


buyer_bot = SmartBuyerBot()


def evaluate_threat_and_trigger_hook(
    entity_id: str,
    message_text: str,
    chat_id: Optional[str] = None,
    platform: str = "whatsapp",
    threat_score: Optional[float] = None,
    is_analyst: bool = False,
    simulation_post_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Hook for chat simulation backends to evaluate incoming message threat keywords
    (such as 'weed', 'coke', 'MDMA', 'chitta', etc.), update the consecutive threshold
    accumulator, and automatically engage the Smart Buyer Bot with the escrow payment
    link sequence upon reaching threshold.
    """
    if is_analyst:
        return None

    text_lower = (message_text or "").lower()
    illicit_keywords = [
        "weed", "coke", "mdma", "chitta", "stuff", "hash", "m-cat", "lsd",
        "stamps", "pills", "score", "malana", "ganja", "charas", "cocaine",
        "ice", "meth", "ketamine", "mephedrone", "heroin", "ecstasy", "shrooms",
        "advance", "token", "upi", "qr", "paytm", "gpay"
    ]
    has_illicit_term = any(kw in text_lower for kw in illicit_keywords)

    effective_score = threat_score if threat_score is not None else (0.85 if has_illicit_term else 0.1)
    is_flagged = bool(has_illicit_term or effective_score >= 0.60)

    state_record = {
        "sender_id": entity_id,
        "chat_id": chat_id or entity_id,
        "threat_score": effective_score,
        "flagged_status": is_flagged,
        "extracted_entities": {
            "narcotics_detected": [w for w in illicit_keywords if w in text_lower],
        },
        "nlp_analysis": {"solicitation_intent": has_illicit_term},
    }

    state_res = state_machine.evaluate_threat_event(state_record)
    current_state = state_res.get("current_state")

    if current_state == STATE_ACTIVE_HONEYPOT_READY or (state_res.get("threshold_reached") and current_state != STATE_PASSIVE_MONITOR):
        return buyer_bot.engage_target(
            entity_id=entity_id,
            chat_id=chat_id or entity_id,
            platform=platform,
            simulation_post_url=simulation_post_url,
            message_text=message_text,
        )
    elif current_state in (STATE_HONEYPOT_ENGAGED, STATE_INVOICE_SENT, STATE_TARGET_GEO_LOCATED, STATE_DISPATCH_INITIATED):
        return buyer_bot.handle_target_reply(
            entity_id=entity_id,
            chat_id=chat_id or entity_id,
            message_text=message_text,
            platform=platform,
            simulation_post_url=simulation_post_url,
        )
    return None
