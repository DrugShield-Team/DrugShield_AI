"""
DrugShield AI - Module 1 Extension: Smart Buyer Persona Honeypot Bot
===================================================================
Module alias exporting the Smart Buyer Bot persona, stateful session
manager, and automated threat trigger hook.
"""

from __future__ import annotations

from src.ingestion.smart_honeypot_bot import (
    SmartBuyerBot,
    buyer_bot,
    evaluate_threat_and_trigger_hook,
    BUYER_PAYMENT_REQUEST_TEMPLATES,
    INITIAL_PAYMENT_CONFIRMATION_TEMPLATES,
    INVOICE_CONFIRMATION_TEMPLATES,
    REPLY_TEMPLATES_PROOF,
    REPLY_TEMPLATES_LOCATION,
    REPLY_TEMPLATES_PAYMENT,
    REPLY_TEMPLATES_CONFIRMATION,
    REPLY_TEMPLATES_DEFAULT,
)

__all__ = [
    "SmartBuyerBot",
    "buyer_bot",
    "evaluate_threat_and_trigger_hook",
    "BUYER_PAYMENT_REQUEST_TEMPLATES",
    "INITIAL_PAYMENT_CONFIRMATION_TEMPLATES",
    "INVOICE_CONFIRMATION_TEMPLATES",
    "REPLY_TEMPLATES_PROOF",
    "REPLY_TEMPLATES_LOCATION",
    "REPLY_TEMPLATES_PAYMENT",
    "REPLY_TEMPLATES_CONFIRMATION",
    "REPLY_TEMPLATES_DEFAULT",
]

