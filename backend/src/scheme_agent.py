import asyncio
import logging
import os
from typing import Optional

from livekit.agents import (
    Agent,
    RunContext,
    function_tool,
)
from livekit.agents.llm import ChatContext

import db
import schemes

logger = logging.getLogger("agent")

SCHEME_FAILURE_FALLBACK = (
    "I'm sorry, I'm currently unable to retrieve the latest scheme information. "
    "Please try again later."
)

DEMO_SESSION_FAILURE_ONCE = True
SIMULATE_DAY5_FAILURE = False


class SchemeSahayak(Agent):
    def __init__(self, user_request: str, chat_ctx: ChatContext) -> None:
        from prompt import SCHEME_SAHAYAK_SYSTEM_PROMPT
        super().__init__(
            instructions=SCHEME_SAHAYAK_SYSTEM_PROMPT,
            chat_ctx=chat_ctx
        )
        self.user_request = user_request
        self.has_simulated_session_failure: bool = False
        self.scheme_checked: bool = False
        self.documents_received: bool = False
        self._intro_played: bool = False

    async def on_enter(self) -> None:
        logger.info(f"SchemeSahayak.on_enter called. User request: {self.user_request}")
        if not self._intro_played:
            self._intro_played = True
            intro_instructions = (
                f"Introduce yourself as SchemeSahayak, the Government Scheme Specialist. "
                f"You must say exactly: "
                f"'Namaste! I'm SchemeSahayak, the Government Scheme Specialist. I understand you need help with your government scheme question. Let's go through it together.' "
                f"Then immediately address their original question: '{self.user_request}'. "
                f"Use check_scheme_eligibility or get_scheme_document_checklist to fetch accurate details. "
                f"Do not ask them to repeat the question."
            )
            await self.session.generate_reply(instructions=intro_instructions)

    @function_tool
    async def lookup_caller(self, context: RunContext, query: str) -> str:
        """Look up a caller in the database by their name or user ID to see if they are a returning caller.

        Args:
            query: The caller's name or user ID to look up.
        """
        logger.info(f"SchemeSahayak looking up caller with query: '{query}'")
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
            logger.info(f"SchemeSahayak successfully saved caller data: {saved_record}")
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

        Args:
            scheme_name: The name or alias of the government scheme (e.g. 'PM Jan Dhan Yojana', 'PM Suraksha Bima Yojana', 'PMSBY', 'PM Jeevan Jyoti Bima Yojana', 'PMJJBY', 'Atal Pension Yojana', 'APY', 'Sukanya Samriddhi Yojana', 'PM SVANidhi', 'PM Mudra Yojana', 'PM Kisan').
            age: The caller's age or beneficiary child's age in years, if provided.
            eligibility_answers: Summary of collected answers from the caller (e.g. 'Occupation: street vendor, Non-taxpayer, has savings bank account').
            occupation: The caller's profession or occupation (e.g. 'street vendor', 'farmer', 'shopkeeper', 'salaried').
            gender: Beneficiary gender (e.g. 'female', 'male') - relevant for girl-child schemes like Sukanya Samriddhi.
            is_taxpayer: True if the caller pays income tax, False if non-taxpayer.
            has_bank_account: Whether the caller already has an active bank account.
        """
        logger.info(
            f"SchemeSahayak evaluating scheme eligibility: scheme='{scheme_name}', age={age}, "
            f"occupation={occupation}, gender={gender}, taxpayer={is_taxpayer}, answers='{eligibility_answers}'"
        )
        logger.info("TOOL CALLED: check_scheme_eligibility")

        try:
            if os.getenv("DAY5_FORCE_TOOL_FAILURE", "false").strip().lower() in ("true", "1", "yes") or SIMULATE_DAY5_FAILURE:
                logger.warning("DAY5_FORCE_TOOL_FAILURE: true")
                logger.warning("TOOL FAILED: Scheme data source temporarily unavailable")
                raise RuntimeError("Scheme data source temporarily unavailable")

            if DEMO_SESSION_FAILURE_ONCE and not self.has_simulated_session_failure:
                self.has_simulated_session_failure = True
                logger.warning(f"DAY5 DEMO: Simulating transient portal timeout on first session call for '{scheme_name}'")
                logger.warning("TOOL FAILED: Scheme data source temporarily unavailable")
                return SCHEME_FAILURE_FALLBACK

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
            if status in ("ELIGIBLE", "INELIGIBLE", "MORE_INFO_NEEDED"):
                self.scheme_checked = True
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
        logger.info(f"SchemeSahayak getting document checklist for scheme: '{scheme_name}'")
        try:
            res = schemes.get_scheme_checklist(scheme_name)
            if not res or not isinstance(res, dict) or not res.get("found"):
                logger.warning(f"Checklist scheme not found or unavailable: {scheme_name}")
                return SCHEME_FAILURE_FALLBACK

            self.documents_received = True
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
    async def create_escalation(
        self,
        context: RunContext,
        caller_name: str,
        issue_type: str,
        summary: str,
        already_checked: str,
        urgency: str,
        user_consent_given: bool = True,
        caller_language: str = "en-IN",
        preferred_follow_up: str = "phone",
        user_id: Optional[str] = None,
    ) -> str:
        """Create a human-in-the-loop escalation ticket when a caller reports possible fraud or requests an unauthorized financial decision.

        Args:
            caller_name: The name of the caller requesting escalation.
            issue_type: Type of escalation ('FRAUD_SUSPECTED' or 'UNAUTHORIZED_FINANCIAL_DECISION').
            summary: Short useful summary of what happened. MUST NOT contain passwords, PINs, OTPs, card or account numbers.
            already_checked: What the agent already verified, advised, or checked.
            urgency: Level of urgency ('HIGH' for fraud / unauthorized debits, 'MEDIUM' or 'LOW' for financial decisions).
            user_consent_given: True if the caller explicitly gave permission to create the escalation ticket. If False, escalation is aborted.
            caller_language: Preferred language of the caller.
            preferred_follow_up: Preferred follow-up method.
            user_id: Optional user ID if known.
        """
        if not user_consent_given:
            logger.info(f"Escalation consent denied by caller '{caller_name}'. Aborting escalation.")
            return "Escalation cancelled: Caller did not give consent to share information or create an escalation ticket."

        logger.info(
            f"SchemeSahayak creating escalation: caller='{caller_name}', issue_type='{issue_type}', "
            f"urgency='{urgency}', language='{caller_language}', follow_up='{preferred_follow_up}'"
        )
        try:
            record = db.save_escalation(
                caller_name=caller_name,
                issue_type=issue_type,
                summary=summary,
                already_checked=already_checked,
                urgency=urgency,
                caller_language=caller_language,
                follow_up_method=preferred_follow_up,
                user_id=user_id,
            )
            ref_id = record["reference_id"]
            logger.info(f"Escalation successfully created with reference ID: {ref_id}")
            return (
                f"Escalation ticket created successfully. Reference ID: {ref_id}. Status: OPEN. "
                f"Please inform the caller of their reference ID ({ref_id}) and explain that our "
                f"human support team will review the issue and follow up via {preferred_follow_up} "
                f"during standard support hours. If there is an urgent risk of financial fraud, "
                f"remind them to contact their bank branch or emergency helpline immediately to block their card or account."
            )
        except Exception as e:
            logger.error(f"Error creating escalation: {e}")
            return f"Failed to create escalation ticket: {str(e)}"

    @function_tool
    async def end_call(
        self,
        context: RunContext,
        reason: str = "user_declined",
    ) -> str:
        """Politely end or disconnect the phone call when the user declines the reminder, opts out of receiving calls, or finishes the conversation.

        Args:
            reason: Reason for ending the call.
        """
        logger.info(f"Ending call upon user request/opt-out. Reason: {reason}")
        asyncio.create_task(self._hangup_after_delay(context))
        return "Call ending initiated. Acknowledge politely and the call will disconnect."

    async def _hangup_after_delay(self, context: RunContext, delay: float = 3.5) -> None:
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
