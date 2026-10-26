import pytest

from src.database.case_store import CaseStore


def test_event_and_case_are_persisted_together(tmp_path):
    store = CaseStore(tmp_path / "cases.sqlite3")
    store.save_event_and_case(
        event_id="event-1",
        channel="instagram",
        conversation_id="conversation-1",
        message_id="message-1",
        event={"text": "example"},
        analysis={"status": "predicted"},
        case_id="case-1",
        report={"summary": {"message_text": "example"}},
        report_sha256="digest",
    )

    assert store.event_exists("instagram", "conversation-1", "message-1") == "event-1"
    assert store.get_case("case-1")["event_id"] == "event-1"


def test_case_creation_failure_rolls_back_event(tmp_path):
    store = CaseStore(tmp_path / "cases.sqlite3")
    with pytest.raises(ValueError):
        store.save_event_and_case(
            event_id="event-1",
            channel="instagram",
            conversation_id="conversation-1",
            message_id="message-1",
            event={"text": "example"},
            analysis={"status": "predicted"},
            case_id="case-1",
            report=None,
            report_sha256=None,
        )

    assert store.event_exists("instagram", "conversation-1", "message-1") is None


def test_review_history_is_appended_and_final_decision_cannot_be_changed(tmp_path):
    store = CaseStore(tmp_path / "cases.sqlite3")
    store.save_event_and_case(
        event_id="event-1",
        channel="instagram",
        conversation_id="conversation-1",
        message_id="message-1",
        event={"text": "example"},
        analysis={},
        case_id="case-1",
        report={"summary": {}},
        report_sha256="digest",
    )

    store.add_review("case-1", "reviewer-1", "further_review", "Need a second look")
    reviewed = store.add_review("case-1", "reviewer-2", "accept", "Reviewed")
    assert [entry["action"] for entry in reviewed["review_history"]] == [
        "further_review", "accept"
    ]
    with pytest.raises(ValueError):
        store.add_review("case-1", "reviewer-3", "dismiss", "Change mind")
