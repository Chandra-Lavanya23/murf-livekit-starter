import os
import shutil
import tempfile
import pytest
import db
from agent import Assistant

@pytest.fixture
def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_analytics.db")
    db.init_db(db_path)
    yield db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_call_analytics_save_and_update(temp_db):
    # Test saving an analytics record
    call_id = "test_call_1"
    channel = "browser"
    outcome = "FAILED"

    record = db.save_call_analytics(
        call_id=call_id,
        channel=channel,
        outcome=outcome,
        db_path=temp_db,
    )

    assert record["call_id"] == call_id
    assert record["channel"] == channel
    assert record["outcome"] == outcome
    assert "timestamp" in record

    # Retrieve metrics
    metrics = db.get_call_metrics(db_path=temp_db)
    assert metrics["total_calls"] == 1
    assert metrics["failed_calls"] == 1
    assert metrics["successful_calls"] == 0

    # Update the record to SUCCESS
    updated_record = db.save_call_analytics(
        call_id=call_id,
        channel=channel,
        outcome="SUCCESS",
        db_path=temp_db,
    )

    assert updated_record["outcome"] == "SUCCESS"

    # Verify metrics updated correctly
    metrics_after = db.get_call_metrics(db_path=temp_db)
    assert metrics_after["total_calls"] == 1
    assert metrics_after["failed_calls"] == 0
    assert metrics_after["successful_calls"] == 1


def test_call_analytics_privacy_isolation(temp_db):
    # Write a call
    db.save_call_analytics("call_safe", "SIP", "SUCCESS", db_path=temp_db)

    # Fetch recent call logs
    recent = db.get_recent_calls(limit=10, db_path=temp_db)
    assert len(recent) == 1
    call = recent[0]

    # Verify strictly safe fields are present
    assert "call_id" in call
    assert "timestamp" in call
    assert "channel" in call
    assert "outcome" in call

    # Verify that NO sensitive columns exist (check list of keys)
    prohibited_fields = {
        "caller_name", "name", "phone", "phone_number", "account", "account_number",
        "otp", "pin", "password", "summary", "transcript", "conversation"
    }
    for field in prohibited_fields:
        assert field not in call


def test_assistant_session_isolation():
    # Instantiate two separate assistants (simulating separate call sessions)
    session_1 = Assistant()
    session_2 = Assistant()

    # Verify initial states
    assert session_1.scheme_checked is False
    assert session_1.documents_received is False
    assert session_2.scheme_checked is False
    assert session_2.documents_received is False

    # Perform action in session 1
    session_1.scheme_checked = True

    # Verify session 1 updated, but session 2 remained isolated
    assert session_1.scheme_checked is True
    assert session_2.scheme_checked is False

    # Perform action in session 2
    session_2.documents_received = True

    # Verify session 2 updated, but session 1 remained isolated
    assert session_2.documents_received is True
    assert session_1.documents_received is False
