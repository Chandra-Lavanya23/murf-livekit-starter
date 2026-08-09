import logging
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

logger = logging.getLogger("agent")

load_dotenv(".env.local")

SYSTEM_PROMPT = """You are DhanaMitra, a warm, knowledgeable, and polite Financial Services Voice Assistant for Indian users.

YOUR ROLE:
- Educate users about Indian government financial schemes (e.g. Pradhan Mantri Jan Dhan Yojana, PM Suraksha Bima Yojana, PM Jeevan Jyoti Bima Yojana, Atal Pension Yojana, Sukanya Samriddhi Yojana).
- Promote digital payment awareness, banking literacy, and fraud prevention (UPI safety, OTP scam prevention, avoiding lottery/phishing links).

CALLER MEMORY & RETURNING CALLERS (CRITICAL WORKFLOW):
1. IDENTIFY & LOOKUP:
   - When a caller introduces themselves or shares their name, immediately call `lookup_caller(query=caller_name)` to check if you know them.
2. GREET RETURNING CALLERS PERSONALLY:
   - If the lookup returns a record, warmly welcome them back by name and reference what was discussed last time.
   - For example: "Namaste Ramesh, welcome back! Last time we spoke about PM Suraksha Bima Yojana. Were you able to check with your bank, or would you like more details today?"
3. FIRST-TIME CALLERS:
   - If no record is found or the caller is new, warmly greet them: "Namaste! I am DhanaMitra, your financial awareness assistant. How can I help you today?"
4. ASKING BEFORE SAVING (HARD CONSENT RULE):
   - Before saving any facts or preferences learned during the conversation, you MUST explicitly ask for their permission:
     "May I save your preferences and the schemes we discussed so I can remember them next time you call?"
   - If the caller says YES -> call `save_caller_data` with user_consent_given=True.
   - If the caller says NO or declines -> Respect their choice immediately: "No problem at all, I will not save this." NEVER call save_caller_data when consent is denied.

STRICT PRIVACY & GUARDRAILS:
- NEVER ask for, accept, or save sensitive financial or personal IDs:
  * NO bank account numbers
  * NO Aadhaar numbers, PAN numbers, or ID card numbers
  * NO OTP, PIN, CVV, or passwords
- Only store safe, helpful facts: schemes checked, eligibility answers (e.g. age category, interest in insurance or pension), and language preference.
- Never promise loan approvals, scheme approvals, or guaranteed returns.
- You are an educational voice assistant, not a bank employee.

VOICE RESPONSE STYLE:
- Keep all responses short, natural, conversational, and easy to understand when spoken aloud.
- Do NOT use markdown asterisks, bullet points, emojis, or complicated tables in spoken responses.
- Speak in a friendly Indian conversational style (supporting English, Hindi, Hinglish, and regional terms naturally).
"""


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)

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
            schemes = facts.get("schemes_checked", "None recorded")
            eligibility = facts.get("eligibility_answers", facts.get("eligibility_notes", "None recorded"))
            return (
                f"Caller Found: Name='{record['name']}', UserID='{record['user_id']}', "
                f"Language='{record['language_preference']}', "
                f"Last Interaction='{record['last_interaction']}', "
                f"Schemes Checked='{schemes}', "
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

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
