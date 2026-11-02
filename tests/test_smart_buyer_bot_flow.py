"""
Unit & Integration Tests for Smart Buyer Bot Hook, Threshold Timing, and Audio Synthesis
"""

from __future__ import annotations

import sys
import tempfile
import pathlib
import uuid

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.cases.state_machine import (
    STATE_PASSIVE_MONITOR,
    STATE_ACTIVE_HONEYPOT_READY,
    STATE_INVOICE_SENT,
    ThreatStateMachine,
    state_machine,
)
from src.ingestion.smart_buyer_bot import (
    SmartBuyerBot,
    buyer_bot,
    evaluate_threat_and_trigger_hook,
)


def test_smart_buyer_bot_alias_and_classes():
    """Verify smart_buyer_bot re-exports all required symbols and instances."""
    assert SmartBuyerBot is not None
    assert buyer_bot is not None
    assert isinstance(buyer_bot, SmartBuyerBot)
    assert callable(evaluate_threat_and_trigger_hook)


def test_four_consecutive_illicit_messages_flow():
    """
    Verify that 4 consecutive messages containing keywords like 'weed', 'coke', 'mdma', 'chitta'
    properly evaluate threat count:
    - Messages 1-3 maintain PASSIVE_MONITOR without bot response.
    - Message 4 triggers the Smart Buyer Bot with the escrow payment link sequence and 5.0s delay.
    """
    tmp_path = pathlib.Path(tempfile.mkdtemp())
    test_db = tmp_path / "test_state.db"
    sm = ThreatStateMachine(db_path=test_db)
    entity_id = f"dealer_target_{uuid.uuid4().hex[:8]}"
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    bot = SmartBuyerBot(api_base_url="http://127.0.0.1:8000")

    # Message 1: "weed"
    ev1 = sm.evaluate_threat_event({
        "sender_id": entity_id,
        "chat_id": chat_id,
        "threat_score": 0.85,
        "flagged_status": True,
        "extracted_entities": {"narcotics_detected": ["weed"]},
    })
    assert ev1["flag_count"] == 1
    assert ev1["current_state"] == STATE_PASSIVE_MONITOR
    assert ev1["threshold_reached"] is False

    # Message 2: "coke"
    ev2 = sm.evaluate_threat_event({
        "sender_id": entity_id,
        "chat_id": chat_id,
        "threat_score": 0.90,
        "flagged_status": True,
        "extracted_entities": {"narcotics_detected": ["coke"]},
    })
    assert ev2["flag_count"] == 2
    assert ev2["current_state"] == STATE_PASSIVE_MONITOR
    assert ev2["threshold_reached"] is False

    # Message 3: "mdma"
    ev3 = sm.evaluate_threat_event({
        "sender_id": entity_id,
        "chat_id": chat_id,
        "threat_score": 0.88,
        "flagged_status": True,
        "extracted_entities": {"narcotics_detected": ["mdma"]},
    })
    assert ev3["flag_count"] == 3
    assert ev3["current_state"] == STATE_PASSIVE_MONITOR
    assert ev3["threshold_reached"] is False

    # Message 4: "chitta" -> 4th consecutive threat breaches threshold!
    ev4 = sm.evaluate_threat_event({
        "sender_id": entity_id,
        "chat_id": chat_id,
        "threat_score": 0.95,
        "flagged_status": True,
        "extracted_entities": {"narcotics_detected": ["chitta"]},
    })
    assert ev4["flag_count"] == 4
    assert ev4["threshold_reached"] is True
    assert ev4["current_state"] == STATE_ACTIVE_HONEYPOT_READY

    # Trigger smart buyer bot on threshold reach
    bot_res = bot.engage_target(
        entity_id=entity_id,
        chat_id=chat_id,
        platform="whatsapp",
        message_text="chitta available rate 3000",
    )
    assert bot_res["entity_id"] == entity_id
    assert "inv_" in bot_res["tracking_token"]
    assert "/api/v1/invoice/" in bot_res["invoice_url"]
    assert bot_res["delay_seconds"] == 5.0
    assert bot_res["initial_confirmation_prompt"] is not None
    assert bot_res["dispatched_message"] is not None
    assert bot_res["invoice_url"] in bot_res["dispatched_message"]

    # Target replies to the escrow link sequence
    reply_res = bot.handle_target_reply(
        entity_id=entity_id,
        chat_id=chat_id,
        message_text="advance sent check rohit@okaxis or QR link",
        platform="whatsapp",
    )
    assert reply_res["stage"] == "INVOICE_SENT"
    assert bot_res["tracking_token"] in reply_res["dispatched_message"]
    assert reply_res["delay_seconds"] == 5.0


def test_evaluate_threat_and_trigger_hook_direct():
    """Verify standalone hook accurately processes illicit terms and handles active state."""
    entity_id = f"dealer_hook_{uuid.uuid4().hex[:8]}"
    chat_id = f"chat_hook_{uuid.uuid4().hex[:8]}"

    # Send 3 non-threshold messages
    for i, word in enumerate(["weed", "coke", "mdma"], start=1):
        res = evaluate_threat_and_trigger_hook(
            entity_id=entity_id,
            message_text=f"I have pure {word} for sale",
            chat_id=chat_id,
            platform="telegram",
        )
        # Messages 1 to 3 do not trigger the bot
        assert res is None, f"Message {i} should maintain passive monitor without bot trigger"

    # 4th consecutive message with "chitta" breaches threshold!
    res4 = evaluate_threat_and_trigger_hook(
        entity_id=entity_id,
        message_text="fresh chitta delivery ready",
        chat_id=chat_id,
        platform="telegram",
    )
    assert res4 is not None
    assert "inv_" in res4["tracking_token"]
    assert res4["delay_seconds"] == 5.0
    assert res4["initial_confirmation_prompt"] is not None
    assert "/api/v1/invoice/" in res4["dispatched_message"]


if __name__ == "__main__":
    test_smart_buyer_bot_alias_and_classes()
    test_four_consecutive_illicit_messages_flow()
    test_evaluate_threat_and_trigger_hook_direct()
    print("ALL SMART BUYER BOT FLOW TESTS PASSED")
