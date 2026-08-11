import asyncio
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    inference,
    room_io,
    tokenize,
)
from livekit.plugins import deepgram, google, murf, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

import db
import schemes

logger = logging.getLogger("agent")

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(backend_dir, ".env.local")
load_dotenv(dotenv_path, override=True)
load_dotenv(".env.local", override=True)
load_dotenv(override=True)

from prompt import SYSTEM_PROMPT

SCHEME_FAILURE_FALLBACK = (
    "I'm sorry, I'm currently unable to retrieve the latest scheme information. "
    "Please try again later."
)

# ==============================================================================
# DAY 5 SESSION FAILURE & RETRY CONFIGURATION
# ------------------------------------------------------------------------------
# In Demo Mode (DEMO_SESSION_FAILURE_ONCE = True):
#   - The FIRST eligibility tool call in a call/session simulates a temporary failure ONCE.
#   - When the user asks to "check again" or "retry", the SECOND tool call in that same
#     session succeeds automatically with real domain data!
#   - When a new call/session starts, the state resets automatically.
#   - No manual environment variable toggling or server restart is needed.
# ==============================================================================
DEMO_SESSION_FAILURE_ONCE = True
SIMULATE_DAY5_FAILURE = False


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        # Resets automatically on each new call/session
        self.has_simulated_session_failure: bool = False

    @function_tool
    async def lookup_caller(self, context: RunContext, query: str) -> str:
        """Look up a caller in the database by their name or user ID to see if they are a returning caller.

        Args:
            query: The caller's name or user ID to look up.
        """
        logger.info(f"Looking up caller with query: '{query}'")
        record = db.get_caller(query)
        if record:
            facts = record.get("facts", {})
            schemes_checked = facts.get("schemes_checked", "None recorded")
            eligibility = facts.get("eligibility_answers", facts.get("eligibility_notes", "None recorded"))
            return (
                f"Caller Found: Name='{record['name']}', UserID='{record['user_id']}', "
                f"Language='{record['language_preference']}', "
                f"Last Interaction='{record['last_interaction']}', "
                f"Schemes Checked='{schemes_checked}', "
                f"Eligibility Answers='{eligibility}'."
            )
        return "Caller not found. This is a new or first-time caller."

    @function_tool
    async def save_caller_data(
        self,
        context: RunContext,
        name: str,
        schemes_checked: str,
        eligibility_answers: str,
        user_consent_given: bool,
        language_preference: str = "en-IN",
        user_id: Optional[str] = None,
    ) -> str:
        """Save the caller's preferences and checked schemes after receiving explicit user consent.

        Args:
            name: The caller's name.
            schemes_checked: The government schemes or financial topics discussed (e.g. 'PM Suraksha Bima Yojana').
            eligibility_answers: Non-sensitive eligibility information (e.g. 'Age 35, interested in accident insurance'). DO NOT store account or ID numbers.
            user_consent_given: MUST be True if the caller explicitly agreed to have their info saved. If False, data will NOT be saved.
            language_preference: Preferred language of the caller (e.g. 'en-IN', 'hi-IN').
            user_id: Optional user ID if already known.
        """
        if not user_consent_given:
            logger.info(f"Consent not given by caller '{name}'. Aborting save.")
            return "Consent was not granted. No caller information was saved."

        facts = {
            "schemes_checked": schemes_checked,
            "eligibility_answers": eligibility_answers,
        }

        try:
            saved_record = db.save_caller(
                name=name,
                language_preference=language_preference,
                facts=facts,
                user_id=user_id,
            )
            logger.info(f"Successfully saved caller data: {saved_record}")
            return f"Caller record saved successfully for {saved_record['name']}."
        except Exception as e:
            logger.error(f"Error saving caller data: {e}")
            return f"Failed to save caller data: {str(e)}"

    @function_tool
    async def check_scheme_eligibility(
        self,
        context: RunContext,
        scheme_name: str,
        age: Optional[int] = None,
        eligibility_answers: Optional[str] = None,
        occupation: Optional[str] = None,
        gender: Optional[str] = None,
        is_taxpayer: Optional[bool] = None,
        has_bank_account: Optional[bool] = None,
    ) -> str:
        """Check whether a caller is eligible for an Indian government financial scheme based on their age and collected eligibility answers.

        CRITICAL REQUIREMENT:
        You have NO internal knowledge of current scheme eligibility rules. You MUST ALWAYS call this tool to determine whether a caller is eligible for any scheme. You must NEVER answer, guess, or evaluate current eligibility from your own memory, system prompt, or prior training data.

        WHEN TO CALL:
        Call this tool whenever a caller asks about their qualification, benefits, or eligibility for ANY supported government financial scheme (e.g. PM Jan Dhan Yojana, PM Suraksha Bima Yojana, PM Jeevan Jyoti Bima Yojana, Atal Pension Yojana, Sukanya Samriddhi Yojana, PM SVANidhi, PM Mudra Yojana, PM-KISAN) after identifying the scheme and collecting the relevant user attributes.

        Args:
            scheme_name: The name or alias of the government scheme (e.g. 'PM Jan Dhan Yojana', 'PM Suraksha Bima Yojana', 'PMSBY', 'PM Jeevan Jyoti Bima Yojana', 'PMJJBY', 'Atal Pension Yojana', 'APY', 'Sukanya Samriddhi Yojana', 'PM SVANidhi', 'PM Mudra Yojana', 'PM Kisan').
            age: The caller's age or beneficiary child's age in years, if provided.
            eligibility_answers: Summary of collected answers from the caller (e.g. 'Occupation: street vendor, Non-taxpayer, has savings bank account').
            occupation: The caller's profession or occupation (e.g. 'street vendor', 'farmer', 'shopkeeper', 'salaried').
            gender: Beneficiary gender (e.g. 'female', 'male') - relevant for girl-child schemes like Sukanya Samriddhi.
            is_taxpayer: True if the caller pays income tax, False if non-taxpayer (critical for Atal Pension Yojana / PM-KISAN).
            has_bank_account: Whether the caller already has an active bank account.
        """
        logger.info(
            f"Evaluating scheme eligibility: scheme='{scheme_name}', age={age}, "
            f"occupation={occupation}, gender={gender}, taxpayer={is_taxpayer}, answers='{eligibility_answers}'"
        )
        logger.info("TOOL CALLED: check_scheme_eligibility")

        try:
            # 1. Force failure if explicitly configured via DAY5_FORCE_TOOL_FAILURE=true
            if os.getenv("DAY5_FORCE_TOOL_FAILURE", "false").strip().lower() in ("true", "1", "yes") or SIMULATE_DAY5_FAILURE:
                logger.warning("DAY5_FORCE_TOOL_FAILURE: true")
                logger.warning("TOOL FAILED: Scheme data source temporarily unavailable")
                print("\n=======================================================", flush=True)
                print("TOOL CALLED: check_scheme_eligibility", flush=True)
                print("DAY5_FORCE_TOOL_FAILURE: true", flush=True)
                print("TOOL FAILED: Scheme data source temporarily unavailable", flush=True)
                print(f"    Scheme requested: '{scheme_name}', Age: {age}", flush=True)
                print("=======================================================\n", flush=True)
                raise RuntimeError("Scheme data source temporarily unavailable")

            # 2. Day 5 Demo Requirement: Simulate temporary failure ONCE on the FIRST eligibility call in this session
            if DEMO_SESSION_FAILURE_ONCE and not self.has_simulated_session_failure:
                self.has_simulated_session_failure = True
                logger.warning(f"DAY5 DEMO: Simulating transient portal timeout on first session call for '{scheme_name}'")
                logger.warning("TOOL FAILED: Scheme data source temporarily unavailable")
                print("\n=======================================================", flush=True)
                print("TOOL CALLED: check_scheme_eligibility (Call #1 in this session)", flush=True)
                print(">>> DAY 5 DEMO: SIMULATED FIRST-CALL TEMPORARY FAILURE <<<", flush=True)
                print(f"    Scheme requested: '{scheme_name}', Age: {age}", flush=True)
                print("    Simulating temporary government portal connection timeout...", flush=True)
                print("    (This failure happens ONCE per session. Next call will succeed automatically)", flush=True)
                print("=======================================================\n", flush=True)
                return SCHEME_FAILURE_FALLBACK

            # 3. Successful real domain evaluation on SECOND attempt / subsequent calls
            logger.info(f"DAY5 DEMO: Subsequent session call - Connecting to verified scheme database for '{scheme_name}'")
            print("\n=======================================================", flush=True)
            print("TOOL CALLED: check_scheme_eligibility (Call #2+ in this session)", flush=True)
            print(">>> DAY 5 DEMO: SUCCESS - REAL SCHEME DATA RETRIEVED <<<", flush=True)
            print(f"    Scheme requested: '{scheme_name}', Age: {age}", flush=True)
            print("=======================================================\n", flush=True)

            res = schemes.evaluate_scheme_eligibility(
                scheme_query=scheme_name,
                age=age,
                occupation=occupation,
                gender=gender,
                is_taxpayer=is_taxpayer,
                has_bank_account=has_bank_account,
                eligibility_answers=eligibility_answers,
            )

            if not res or not isinstance(res, dict) or not res.get("found"):
                logger.warning(f"Scheme not found or empty/unavailable data for: {scheme_name}")
                return SCHEME_FAILURE_FALLBACK

            status = res.get("status")
            data_date = res.get("guidelines_date", "August 2024")
            scheme_full_name = res.get("scheme_name", scheme_name)
            eligibility_result = res.get("eligibility_result", "")
            reasons_str = " ".join(res.get("reasons", []))
            conditions_list = res.get("important_conditions", [])
            conditions_str = "; ".join(conditions_list) if conditions_list else "Standard bank KYC requirements apply."
            benefits = res.get("benefits", {})
            premium_text = benefits.get("premium", "")
            coverage_text = benefits.get("coverage", "")

            if status == "ELIGIBLE":
                return (
                    f"Scheme Name: {scheme_full_name}. "
                    f"Eligibility Result: {eligibility_result} "
                    f"Reason: {reasons_str}. "
                    f"Important Conditions: {conditions_str}. "
                    f"Benefits & Cost: Premium/Cost: {premium_text}; Benefit/Coverage: {coverage_text}. "
                    f"Source/Update Date: Official Government Guidelines as of {data_date}."
                )
            elif status == "INELIGIBLE":
                return (
                    f"Scheme Name: {scheme_full_name}. "
                    f"Eligibility Result: {eligibility_result} "
                    f"Reason: {reasons_str}. "
                    f"Important Conditions: {conditions_str}. "
                    f"Target Group: {res.get('target_group')}. "
                    f"Source/Update Date: Official Government Guidelines as of {data_date}."
                )
            elif status == "MORE_INFO_NEEDED":
                missing = ", ".join(res.get("missing_criteria", []))
                return (
                    f"Scheme Name: {scheme_full_name}. "
                    f"Eligibility Result: {eligibility_result} "
                    f"Missing Information: Please ask the caller for: {missing}. "
                    f"General Eligibility Target: {res.get('target_group')}. "
                    f"Important Conditions: {conditions_str}. "
                    f"Source/Update Date: Official Government Guidelines as of {data_date}."
                )
            else:
                return SCHEME_FAILURE_FALLBACK

        except Exception as e:
            logger.error(f"Error evaluating scheme eligibility for '{scheme_name}': {e}")
            return SCHEME_FAILURE_FALLBACK

    @function_tool
    async def get_scheme_document_checklist(
        self,
        context: RunContext,
        scheme_name: str,
    ) -> str:
        """Get the official checklist of required documents and application procedure to apply for an Indian government financial scheme (e.g. PM Jan Dhan Yojana, PMSBY, PMJJBY, APY, Sukanya Samriddhi, PM SVANidhi, PM Mudra, PM-KISAN).

        Args:
            scheme_name: Name of the scheme (e.g. 'PM Jan Dhan Yojana', 'PM Suraksha Bima', 'Atal Pension Yojana', 'PM SVANidhi', 'Sukanya Samriddhi', 'Mudra Loan', 'PM Kisan').
        """
        logger.info(f"Getting document checklist for scheme: '{scheme_name}'")
        try:
            res = schemes.get_scheme_checklist(scheme_name)
            if not res or not isinstance(res, dict) or not res.get("found"):
                logger.warning(f"Checklist scheme not found or unavailable: {scheme_name}")
                return SCHEME_FAILURE_FALLBACK

            docs = "; ".join(res.get("documents", []))
            data_date = res.get("guidelines_date", "August 2024")
            conditions = "; ".join(res.get("important_conditions", []))
            return (
                f"Document Checklist for {res.get('scheme_name', scheme_name)} (Official Guidelines as of {data_date}): "
                f"Required Documents: {docs}. "
                f"Important Conditions: {conditions}. "
                f"Application Method: {res.get('application_process')}. "
                f"Safety Note: {res.get('privacy_notice')}"
            )
        except Exception as e:
            logger.error(f"Error getting document checklist for '{scheme_name}': {e}")
            return SCHEME_FAILURE_FALLBACK

    @function_tool
    async def end_call(
        self,
        context: RunContext,
        reason: str = "user_declined",
    ) -> str:
        """Politely end or disconnect the phone call when the user declines the reminder, opts out of receiving calls, or finishes the conversation.
        
        Args:
            reason: Reason for ending the call (e.g. 'user_opted_out', 'user_declined', 'call_finished').
        """
        logger.info(f"Ending call upon user request/opt-out. Reason: {reason}")
        # Disconnect the room after short delay so farewell utterance finishes playing
        asyncio.create_task(self._hangup_after_delay(context))
        return "Call ending initiated. Acknowledge politely and the call will disconnect."

    async def _hangup_after_delay(self, context: RunContext, delay: float = 3.5) -> None:
        """Helper to disconnect the room session after allowing TTS playout."""
        try:
            await asyncio.sleep(delay)
            if (
                hasattr(context, "session")
                and context.session
                and hasattr(context.session, "room")
                and context.session.room
            ):
                logger.info("Disconnecting room after user opt-out/call termination.")
                await context.session.room.disconnect()
        except Exception as e:
            logger.warning(f"Error during delayed hangup: {e}")


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    # Logging setup
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using Murf Falcon, Gemini, Deepgram, and the LiveKit turn detector
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),
        tts=murf.TTS(
            voice="Anisha",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    # Check if this room session is an outbound call
    is_outbound = (
        ctx.room.name.startswith("outbound-")
        or ctx.room.name.startswith("sip-outbound-")
        or (ctx.room.metadata and "outbound" in ctx.room.metadata.lower())
    )

    if is_outbound:
        logger.info(f"Outbound calling session active for room '{ctx.room.name}'.")
        has_spoken_opening = False

        async def deliver_outbound_opening():
            nonlocal has_spoken_opening
            if has_spoken_opening:
                return
            has_spoken_opening = True
            # Wait briefly for audio streaming connection to stabilize
            await asyncio.sleep(1.0)
            opening_text = (
                "Hello, this is DhanaMitra, a financial services assistant. I'm calling to "
                "remind you about an upcoming deadline related to a government financial "
                "scheme you were previously found eligible for. If you'd like to hear more, "
                "say yes. If you don't want to receive these calls, say no."
            )
            logger.info("Delivering Day 6 outbound opening prompt to participant.")
            await session.say(opening_text, allow_interruptions=True)

        @ctx.room.on("participant_connected")
        def on_participant_connected(participant: rtc.RemoteParticipant):
            logger.info(f"Participant connected to outbound room: {participant.identity}")
            asyncio.create_task(deliver_outbound_opening())

    # Join the room and connect to the user
    await ctx.connect()

    if is_outbound and ctx.room.remote_participants:
        logger.info("Remote participant already in room upon connect. Triggering opening.")
        asyncio.create_task(deliver_outbound_opening())


if __name__ == "__main__":
    cli.run_app(server)

