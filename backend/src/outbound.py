"""Day 6 Outbound Calling Script for DhanaMitra Financial Services Voice Assistant.

This script initiates outbound SIP/telephony calls via LiveKit to deliver
proactive government financial scheme deadline reminders to eligible callers.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import uuid
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from livekit import api

# Attempt to load local db helper for personalized caller lookups
try:
    import db
except ImportError:
    # If run from outside backend/src
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import db  # type: ignore

# -----------------------------------------------------------------------------
# Configuration & Environment Loading
# -----------------------------------------------------------------------------
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(backend_dir, ".env.local")
load_dotenv(dotenv_path, override=True)
load_dotenv(".env.local", override=True)
load_dotenv(override=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("outbound")

# Standard Day 6 Outbound Disclosure & Opening Prompt
OUTBOUND_OPENING_PROMPT = (
    "Hello, this is DhanaMitra, a financial services assistant. I'm calling to "
    "remind you about an upcoming deadline related to a government financial "
    "scheme you were previously found eligible for. If you'd like to hear more, "
    "say yes. If you don't want to receive these calls, say no."
)


def format_sip_destination(dest: str) -> str:
    """Formats destination to the SIP user or phone number expected by LiveKit sip_call_to.
    
    LiveKit requires a phone number or SIP user, not a full SIP URI.
    
    Examples:
      'sip:alice@sip.linphone.org' -> 'alice'
      'alice@sip.linphone.org'     -> 'alice'
      'sip:alice'                  -> 'alice'
      '+919876543210'              -> '+919876543210'
      'alice'                      -> 'alice'
    """
    if not dest:
        return ""
    clean = str(dest).strip()
    
    # Strip leading sip: or sips:
    if clean.lower().startswith("sips:"):
        clean = clean[5:]
    elif clean.lower().startswith("sip:"):
        clean = clean[4:]
        
    # Extract user before @ if a domain is attached
    if "@" in clean:
        clean = clean.split("@", 1)[0]
        
    return clean.strip()


def mask_phone_number(phone_or_sip: str) -> str:
    """Masks middle digits/chars of a phone number or SIP user/URI to ensure privacy in logs.
    
    Examples:
      +919876543210 -> +91 98****3210
      9876543210    -> 98****3210
      sip:alice@domain.com -> sip:a***e@domain.com
      alice         -> a***e
    """
    if not phone_or_sip:
        return "[EMPTY]"
    
    clean = str(phone_or_sip).strip()
    
    # Handle SIP URI format (e.g. sip:alice@sip.linphone.org)
    if clean.lower().startswith("sip:") or "@" in clean:
        prefix = "sip:" if clean.lower().startswith("sip:") else ""
        raw = clean[4:] if clean.lower().startswith("sip:") else clean
        if "@" in raw:
            user, domain = raw.split("@", 1)
            domain_part = f"@{domain}"
        else:
            user = raw
            domain_part = ""
        
        if len(user) <= 2:
            masked_user = "**"
        else:
            masked_user = f"{user[0]}***{user[-1]}"
        return f"{prefix}{masked_user}{domain_part}"
    
    # Handle phone numbers
    digits = re.sub(r"[^\d+]", "", clean)
    if len(digits) >= 10:
        prefix = digits[:4]
        suffix = digits[-4:]
        mask_len = max(len(digits) - 8, 2)
        return f"{prefix}{'*' * mask_len}{suffix}"
    elif len(digits) >= 6:
        return f"{digits[:2]}{'*' * (len(digits) - 4)}{digits[-2:]}"
    elif digits:
        return f"***{digits[-2:]}" if len(digits) >= 2 else "***"
    
    # Non-digit username (e.g. 'alice')
    if len(clean) <= 2:
        return "**"
    return f"{clean[0]}***{clean[-1]}"


def get_env_variable(var_name: str, fallback_names: Optional[list[str]] = None, default: Optional[str] = None) -> Optional[str]:
    """Retrieves an environment variable with optional fallbacks."""
    val = os.getenv(var_name)
    if val and val.strip():
        return val.strip()
    
    if fallback_names:
        for fb in fallback_names:
            fb_val = os.getenv(fb)
            if fb_val and fb_val.strip():
                return fb_val.strip()
                
    return default


def validate_environment(trunk_id: Optional[str], phone_number: Optional[str]) -> None:
    """Validates that all required LiveKit credentials and SIP configs are present."""
    livekit_url = get_env_variable("LIVEKIT_URL")
    api_key = get_env_variable("LIVEKIT_API_KEY")
    api_secret = get_env_variable("LIVEKIT_API_SECRET")

    missing = []
    if not livekit_url:
        missing.append("LIVEKIT_URL")
    if not api_key:
        missing.append("LIVEKIT_API_KEY")
    if not api_secret:
        missing.append("LIVEKIT_API_SECRET")

    if missing:
        err_msg = (
            f"Missing required LiveKit configuration in environment: {', '.join(missing)}.\n"
            f"Please ensure backend/.env.local contains:\n"
            f"  LIVEKIT_URL=wss://your-project.livekit.cloud\n"
            f"  LIVEKIT_API_KEY=your_key\n"
            f"  LIVEKIT_API_SECRET=your_secret\n"
        )
        logger.error(err_msg)
        raise ValueError(err_msg)

    if not trunk_id or not str(trunk_id).strip():
        err_msg = (
            "SIP outbound trunk ID is not configured.\n"
            "Please set SIP_OUTBOUND_TRUNK_ID (or LIVEKIT_SIP_TRUNK_ID) in backend/.env.local "
            "or pass --trunk <TRUNK_ID> via command line."
        )
        logger.error("SIP outbound trunk ID is not configured.")
        raise ValueError("SIP outbound trunk ID is not configured.")

    if not phone_number or not str(phone_number).strip():
        err_msg = (
            "Destination phone number or SIP URI is not configured.\n"
            "Please set OUTBOUND_PHONE_NUMBER (or LINPHONE_SIP_URI) in backend/.env.local "
            "or pass --phone <NUMBER_OR_SIP> via command line."
        )
        logger.error("Destination phone number or SIP URI is not configured.")
        raise ValueError("Destination phone number or SIP URI is not configured.")


async def make_outbound_call(
    phone_number: str,
    trunk_id: str,
    caller_name: Optional[str] = None,
    scheme_name: Optional[str] = None,
    deadline_info: Optional[str] = None,
    room_name: Optional[str] = None,
    wait_until_answered: bool = False,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """Places an outbound SIP call using LiveKit SIP Service.
    
    Args:
        phone_number: Destination phone number or SIP URI (e.g. +919876543210 or sip:...).
        trunk_id: LiveKit Outbound SIP Trunk ID (e.g. ST_...).
        caller_name: Optional name of the user to greet.
        scheme_name: Optional scheme previously checked (e.g. 'Atal Pension Yojana').
        deadline_info: Optional reminder detail (e.g. 'May 31st annual auto-debit renewal').
        room_name: Optional room name; generates a unique outbound room if None.
        wait_until_answered: Whether to block until the call is answered.
        timeout_seconds: Timeout for the API request in seconds.

    Returns:
        Dict containing call details and SIP participant info.
    """
    # Validate environment & parameters
    validate_environment(trunk_id, phone_number)

    livekit_url = get_env_variable("LIVEKIT_URL")
    api_key = get_env_variable("LIVEKIT_API_KEY")
    api_secret = get_env_variable("LIVEKIT_API_SECRET")

    # Format destination for LiveKit SIP API (expects phone number or SIP user, not full URI)
    sip_destination = format_sip_destination(phone_number)

    # Generate room name if not specified
    if not room_name:
        short_id = uuid.uuid4().hex[:8]
        room_name = f"outbound-call-{short_id}"

    # Auto-lookup caller context from DB if caller_name is provided or known
    db_record = None
    if caller_name:
        try:
            db_record = db.get_caller(caller_name)
            if db_record and not scheme_name:
                facts = db_record.get("facts", {})
                scheme_name = facts.get("schemes_checked")
        except Exception as e:
            logger.warning(f"Could not load caller record from DB: {e}")

    # Build metadata payload for agent context injection
    metadata_payload = {
        "call_type": "outbound",
        "caller_name": caller_name or "Valued Caller",
        "scheme_name": scheme_name or "Government Financial Scheme",
        "deadline_info": deadline_info or "upcoming renewal and enrollment deadline",
        "opening_text": OUTBOUND_OPENING_PROMPT,
    }

    masked_num = mask_phone_number(phone_number)
    masked_dest = mask_phone_number(sip_destination)
    logger.info("=" * 65)
    logger.info(">>> INITIATING DAY 6 OUTBOUND CALL <<<")
    logger.info(f"  Target Destination : {masked_num}")
    logger.info(f"  SIP Call To (User) : {masked_dest}")
    logger.info(f"  Trunk ID           : {trunk_id}")
    logger.info(f"  Room Name          : {room_name}")
    logger.info(f"  Caller Name        : {caller_name or 'Not specified'}")
    logger.info(f"  Scheme Topic       : {scheme_name or 'General Financial Scheme'}")
    logger.info("=" * 65)

    clean_identity = f"sip_{re.sub(r'[^a-zA-Z0-9]', '_', sip_destination)[-8:]}_{uuid.uuid4().hex[:4]}"
    participant_name = caller_name if caller_name else "Outbound Caller"

    request = api.CreateSIPParticipantRequest(
        sip_trunk_id=trunk_id.strip(),
        sip_call_to=sip_destination,
        room_name=room_name,
        participant_identity=clean_identity,
        participant_name=participant_name,
        participant_metadata=json.dumps(metadata_payload),
        participant_attributes={
            "call_type": "outbound",
            "caller_name": caller_name or "",
            "scheme_name": scheme_name or "",
        },
        play_dialtone=True,
        wait_until_answered=wait_until_answered,
    )

    try:
        async with api.LiveKitAPI(livekit_url, api_key, api_secret) as lkapi:
            # 1. Dispatch "my-agent" to the outbound room
            logger.info(f"Dispatching agent 'my-agent' to room '{room_name}'...")
            dispatch_req = api.CreateAgentDispatchRequest(
                agent_name="my-agent",
                room=room_name,
                metadata=json.dumps(metadata_payload),
            )
            dispatch_info = await lkapi.agent_dispatch.create_dispatch(dispatch_req)
            dispatch_id = getattr(dispatch_info, "id", "")
            logger.info(
                f"Agent dispatched successfully: agent_name='my-agent', room_name='{room_name}', "
                f"dispatch_id='{dispatch_id}'"
            )

            # 2. Place outbound SIP call in the SAME room
            logger.info("Connecting to LiveKit SIP Service and placing call...")
            participant_info = await asyncio.wait_for(
                lkapi.sip.create_sip_participant(request),
                timeout=timeout_seconds,
            )

            result = {
                "status": "SUCCESS",
                "room_name": room_name,
                "agent_name": "my-agent",
                "dispatch_id": dispatch_id,
                "participant_id": getattr(participant_info, "participant_id", ""),
                "participant_identity": getattr(participant_info, "participant_identity", clean_identity),
                "sip_call_id": getattr(participant_info, "sip_call_id", ""),
                "destination_masked": masked_num,
                "trunk_id": trunk_id,
            }

            logger.info("-------------------------------------------------------------")
            logger.info(">>> OUTBOUND CALL SUCCESSFULLY DISPATCHED <<<")
            logger.info(f"  Room Name      : {result['room_name']}")
            logger.info(f"  Participant ID : {result['participant_id']}")
            logger.info(f"  SIP Call ID    : {result['sip_call_id']}")
            logger.info(f"  Connection     : Agent will join room and deliver opening")
            logger.info("-------------------------------------------------------------")
            return result

    except asyncio.TimeoutError:
        err_msg = (
            f"Outbound call timed out after {timeout_seconds} seconds. "
            f"Check network connectivity to LiveKit server ({livekit_url})."
        )
        logger.error(f"CALL FAILED: {err_msg}")
        raise TimeoutError(err_msg) from None

    except Exception as e:
        logger.error(f"CALL FAILED: Error creating SIP participant: {str(e)}")
        logger.error("Troubleshooting tips:")
        logger.error("  1. Check that your SIP Outbound Trunk ID is active in LiveKit Cloud.")
        logger.error("  2. Verify that the destination phone number / SIP URI format is supported.")
        logger.error("  3. Ensure the backend agent worker is running: `python src/agent.py dev`")
        raise


def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments with environment variable fallbacks."""
    parser = argparse.ArgumentParser(
        description="Day 6 Outbound Calling Script for DhanaMitra Financial Services Voice Assistant"
    )
    
    parser.add_argument(
        "--to",
        "--phone",
        dest="phone",
        default=get_env_variable(
            "OUTBOUND_PHONE_NUMBER",
            fallback_names=["LINPHONE_SIP_URI", "SIP_CALL_TO", "DESTINATION_PHONE_NUMBER", "PHONE_NUMBER"],
        ),
        help="Destination phone number (E.164 format, e.g. +919876543210) or SIP URI (e.g. sip:alice@sip.linphone.org).",
    )
    
    parser.add_argument(
        "--trunk",
        dest="trunk_id",
        default=get_env_variable(
            "SIP_OUTBOUND_TRUNK_ID",
            fallback_names=["LIVEKIT_SIP_TRUNK_ID", "SIP_TRUNK_ID"],
        ),
        help="LiveKit Outbound SIP Trunk ID (e.g. ST_xxxxxxxxx).",
    )
    
    parser.add_argument(
        "--name",
        dest="caller_name",
        default=get_env_variable("OUTBOUND_CALLER_NAME", default=""),
        help="Optional caller name for personalized greeting & DB memory lookup (e.g. 'Lavanya').",
    )
    
    parser.add_argument(
        "--scheme",
        dest="scheme_name",
        default=get_env_variable("OUTBOUND_SCHEME_NAME", default=""),
        help="Optional scheme name for the deadline reminder (e.g. 'Atal Pension Yojana').",
    )
    
    parser.add_argument(
        "--deadline",
        dest="deadline_info",
        default="May 31st annual auto-debit renewal",
        help="Deadline detail for the reminder.",
    )
    
    parser.add_argument(
        "--room",
        dest="room_name",
        default=None,
        help="Optional specific LiveKit room name to join.",
    )
    
    parser.add_argument(
        "--wait-answered",
        action="store_true",
        default=False,
        help="Wait until the SIP participant answers before exiting script.",
    )
    
    return parser.parse_args()


def main() -> None:
    """Main entrypoint for CLI execution."""
    args = parse_arguments()
    
    try:
        asyncio.run(
            make_outbound_call(
                phone_number=args.phone,
                trunk_id=args.trunk_id,
                caller_name=args.caller_name if args.caller_name else None,
                scheme_name=args.scheme_name if args.scheme_name else None,
                deadline_info=args.deadline_info,
                room_name=args.room_name,
                wait_until_answered=args.wait_answered,
            )
        )
    except KeyboardInterrupt:
        logger.info("Outbound call execution cancelled by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Execution terminated with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
