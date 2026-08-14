import os
import shutil
import tempfile
import pytest
from livekit.agents import AgentSession, inference, llm

import db
from agent import Assistant
from scheme_agent import SchemeSahayak


def _llm() -> llm.LLM:
    # Use the test framework's LLM model configuration
    return inference.LLM(model="openai/gpt-4.1-mini")


@pytest.fixture
def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_handoff_callers.db")
    db.init_db(db_path)
    yield db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_normal_question_no_handoff() -> None:
    """Verify that a normal safety question is answered by DhanaMitra without handoff."""
    async with (
        _llm() as test_llm,
        AgentSession(llm=test_llm) as session,
    ):
        assistant = Assistant()
        await session.start(assistant)

        # User asks about digital payment safety
        result = await session.run(user_input="What is digital payment safety?")

        # Evaluate the response
        await (
            result.expect.next_event()
            .is_message(role="assistant")
            .judge(
                test_llm,
                intent="Educates the user about digital payment safety or financial awareness.",
            )
        )

        # Ensure no more events (no tool calls / handoff triggered)
        result.expect.no_more_events()
        
        # Verify active agent remains Assistant
        assert isinstance(session.current_agent, Assistant)


@pytest.mark.asyncio
async def test_specialist_handoff_and_intro() -> None:
    """Verify that a scheme question triggers handoff and SchemeSahayak introduces itself."""
    async with (
        _llm() as test_llm,
        AgentSession(llm=test_llm) as session,
    ):
        assistant = Assistant()
        await session.start(assistant)

        # User asks about PM Kisan
        result = await session.run(
            user_input="I want to know whether I am eligible for PM Kisan and what documents I need."
        )

        # The assistant must say the handoff message
        await (
            result.expect.next_event()
            .is_message(role="assistant")
            .judge(
                test_llm,
                intent="""
                Announces the handoff to the Government Scheme Specialist.
                Must mention that they will connect the user to the Government Scheme Specialist
                and that the user won't need to repeat their question.
                """,
            )
        )

        # The assistant must call the handoff tool
        result.expect.next_event().is_function_call(name="handoff_to_scheme_specialist")

        # The new agent (SchemeSahayak) should be handed off to
        handoff_ev = result.expect.next_event(type="agent_handoff").event()
        assert isinstance(handoff_ev.new_agent, SchemeSahayak)

        # The new agent (SchemeSahayak) should run on_enter and greet the user
        await (
            result.expect.next_event(type="message")
            .judge(
                test_llm,
                intent="""
                Introduces itself as SchemeSahayak, the Government Scheme Specialist.
                Acknowledges the user's question about PM Kisan eligibility and documents.
                """,
            )
        )

        # Verify agent switched to SchemeSahayak
        assert isinstance(session.current_agent, SchemeSahayak)
        # Check context preservation on SchemeSahayak
        assert "PM Kisan" in session.current_agent.user_request


@pytest.mark.asyncio
async def test_scheme_sahayak_tools() -> None:
    """Verify that SchemeSahayak can execute scheme eligibility and document checklist tools."""
    # Test checking eligibility
    specialist = SchemeSahayak(user_request="PM Kisan", chat_ctx=llm.ChatContext())
    assert specialist.scheme_checked is False
    
    eligibility_result = await specialist.check_scheme_eligibility(
        context=None,
        scheme_name="PM Kisan",
        age=35,
        is_taxpayer=False,
    )
    # The first call in DEMO simulates temporary failure/timeout
    assert "unable to retrieve" in eligibility_result or "failure" in eligibility_result.lower()
    
    # Second call succeeds
    success_result = await specialist.check_scheme_eligibility(
        context=None,
        scheme_name="PM Kisan",
        age=35,
        is_taxpayer=False,
    )
    assert "PM Kisan" in success_result
    assert specialist.scheme_checked is True

    # Test document checklist tool
    checklist_result = await specialist.get_scheme_document_checklist(
        context=None,
        scheme_name="PM Kisan",
    )
    assert "PM Kisan" in checklist_result
    assert specialist.documents_received is True


@pytest.mark.asyncio
async def test_scheme_sahayak_escalation(monkeypatch, temp_db) -> None:
    """Verify that SchemeSahayak handles HITL escalations for fraud/unauthorized actions."""
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", temp_db)
    specialist = SchemeSahayak(user_request="PM Kisan", chat_ctx=llm.ChatContext())

    escalation_res = await specialist.create_escalation(
        context=None,
        caller_name="Ravi Kumar",
        issue_type="FRAUD_SUSPECTED",
        summary="Caller reports scam message asking for PM Kisan details",
        already_checked="Advised caller to freeze account",
        urgency="HIGH",
        user_consent_given=True,
    )

    assert "Reference ID: ESC-" in escalation_res
    assert "Status: OPEN" in escalation_res

    # Check database
    records = db.list_escalations(db_path=temp_db)
    assert len(records) == 1
    assert records[0]["caller_name"] == "Ravi Kumar"
    assert records[0]["issue_type"] == "FRAUD_SUSPECTED"


def test_handoff_analytics(temp_db):
    """Verify that analytics outcomes are tracked correctly under handoff without duplicate calls."""
    # Initially 0 calls
    metrics = db.get_call_metrics(db_path=temp_db)
    assert metrics["total_calls"] == 0

    # Save initial analytics record as FAILED (simulating call started)
    db.save_call_analytics(call_id="call_handoff_1", channel="browser", outcome="FAILED", db_path=temp_db)
    metrics = db.get_call_metrics(db_path=temp_db)
    assert metrics["total_calls"] == 1
    assert metrics["failed_calls"] == 1

    # Simulate handoff and checking eligibility on SchemeSahayak
    specialist = SchemeSahayak(user_request="PM Kisan", chat_ctx=llm.ChatContext())
    specialist.scheme_checked = True

    # Update analytics outcome to SUCCESS (simulating room disconnected check)
    assistant = Assistant() # original assistant
    
    # Simulate checking both original assistant and current active agent (SchemeSahayak)
    outcome = "FAILED"
    current_active = specialist
    if (
        getattr(assistant, "scheme_checked", False)
        or getattr(assistant, "documents_received", False)
        or (current_active and getattr(current_active, "scheme_checked", False))
        or (current_active and getattr(current_active, "documents_received", False))
    ):
        outcome = "SUCCESS"

    db.save_call_analytics(call_id="call_handoff_1", channel="browser", outcome=outcome, db_path=temp_db)

    # Verify metrics updated to SUCCESS and total calls is still 1 (no duplicate record)
    metrics_final = db.get_call_metrics(db_path=temp_db)
    assert metrics_final["total_calls"] == 1
    assert metrics_final["failed_calls"] == 0
    assert metrics_final["successful_calls"] == 1
