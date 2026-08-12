import os
import re
import shutil
import tempfile
import pytest
import db
from agent import Assistant


@pytest.fixture
def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_escalations.db")
    db.init_db(db_path)
    yield db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_generate_escalation_id_format():
    ref_id = db.generate_escalation_id()
    assert ref_id.startswith("ESC-")
    assert len(ref_id) == 10
    # Must match ESC- followed by 6 alphanumeric characters
    assert re.match(r"^ESC-[A-Z0-9]{6}$", ref_id)


def test_save_and_get_escalation_fraud(temp_db):
    record = db.save_escalation(
        caller_name="Ramesh Kumar",
        issue_type="FRAUD_SUSPECTED",
        summary="Caller noticed unauthorized ₹5,000 debit from savings account",
        already_checked="Advised caller to contact bank immediately to freeze card/account",
        urgency="HIGH",
        caller_language="hi-IN",
        follow_up_method="phone call",
        db_path=temp_db,
    )

    assert "reference_id" in record
    assert record["reference_id"].startswith("ESC-")
    assert record["caller_name"] == "Ramesh Kumar"
    assert record["issue_type"] == "FRAUD_SUSPECTED"
    assert record["status"] == "OPEN"
    assert record["urgency"] == "HIGH"
    assert record["caller_language"] == "hi-IN"
    assert record["follow_up_method"] == "phone call"
    assert "created_at" in record

    # Retrieve by ID
    fetched = db.get_escalation(record["reference_id"], db_path=temp_db)
    assert fetched is not None
    assert fetched["reference_id"] == record["reference_id"]
    assert fetched["status"] == "OPEN"
    assert fetched["caller_name"] == "Ramesh Kumar"


def test_save_and_get_escalation_unauthorized_financial_decision(temp_db):
    record = db.save_escalation(
        caller_name="Meera Devi",
        issue_type="UNAUTHORIZED_FINANCIAL_DECISION",
        summary="Caller requested immediate direct loan approval and interest waiver for Mudra loan",
        already_checked="Explained agent is an educational assistant and cannot disburse loans or waive interest",
        urgency="MEDIUM",
        caller_language="en-IN",
        follow_up_method="branch visit",
        db_path=temp_db,
    )

    assert record["reference_id"].startswith("ESC-")
    assert record["status"] == "OPEN"
    assert record["issue_type"] == "UNAUTHORIZED_FINANCIAL_DECISION"
    assert record["follow_up_method"] == "branch visit"

    # Test list_escalations
    open_list = db.list_escalations(status="OPEN", db_path=temp_db)
    assert len(open_list) == 1
    assert open_list[0]["reference_id"] == record["reference_id"]


def test_privacy_guardrails_redact_sensitive_data_in_escalation(temp_db):
    unsafe_summary = (
        "Caller reported fraud on card 4111222233334444 and account 987654321012345. "
        "Shared OTP: 981234 and password 123456 with scammer. Aadhaar: 1234 5678 9012, PAN: ABCDE1234F"
    )
    unsafe_checks = "Checked account 112233445566 with PIN 4321"

    record = db.save_escalation(
        caller_name="Sunil Sharma",
        issue_type="FRAUD_SUSPECTED",
        summary=unsafe_summary,
        already_checked=unsafe_checks,
        db_path=temp_db,
    )

    saved_summary = record["summary"]
    saved_checks = record["already_checked"]

    # Verify no raw sensitive numbers/credentials exist in stored summary or checks
    assert "4111222233334444" not in saved_summary
    assert "987654321012345" not in saved_summary
    assert "1234 5678 9012" not in saved_summary
    assert "ABCDE1234F" not in saved_summary
    assert "981234" not in saved_summary
    assert "112233445566" not in saved_checks

    assert "[REDACTED" in saved_summary
    assert "[REDACTED" in saved_checks


@pytest.mark.asyncio
async def test_assistant_create_escalation_tool_with_consent(monkeypatch, temp_db):
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", temp_db)
    assistant = Assistant()

    tool_result = await assistant.create_escalation(
        context=None,
        caller_name="Kavita Reddy",
        issue_type="FRAUD_SUSPECTED",
        summary="Suspicious phone call asking for OTP and unexpected debit",
        already_checked="Warned caller not to share OTP, advised checking with bank branch",
        urgency="HIGH",
        user_consent_given=True,
        caller_language="te-IN",
        preferred_follow_up="phone call",
    )

    assert "Escalation ticket created successfully" in tool_result
    assert "Reference ID: ESC-" in tool_result
    assert "Status: OPEN" in tool_result
    assert "standard support hours" in tool_result

    # Check DB entry
    all_escalations = db.list_escalations(db_path=temp_db)
    assert len(all_escalations) == 1
    assert all_escalations[0]["caller_name"] == "Kavita Reddy"
    assert all_escalations[0]["status"] == "OPEN"
    assert all_escalations[0]["caller_language"] == "te-IN"


@pytest.mark.asyncio
async def test_assistant_create_escalation_tool_denied_consent(monkeypatch, temp_db):
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", temp_db)
    assistant = Assistant()

    tool_result = await assistant.create_escalation(
        context=None,
        caller_name="Vikram Singh",
        issue_type="FRAUD_SUSPECTED",
        summary="Caller noticed unauthorized debit but declined escalation",
        already_checked="Advised branch visit",
        urgency="HIGH",
        user_consent_given=False,
    )

    assert "Escalation cancelled" in tool_result
    assert "Caller did not give consent" in tool_result

    # Check DB entry -> Nothing should be saved
    all_escalations = db.list_escalations(db_path=temp_db)
    assert len(all_escalations) == 0
