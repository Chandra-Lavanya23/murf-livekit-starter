import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("db")

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(DB_DIR, "callers.db")

# Prohibited sensitive keys and pattern matchers for Financial Services guardrails
PROHIBITED_KEYS = {
    "account_number",
    "bank_account",
    "account_no",
    "acc_num",
    "aadhaar",
    "aadhaar_number",
    "pan",
    "pan_number",
    "id_number",
    "id_num",
    "card_number",
    "debit_card",
    "credit_card",
    "cvv",
    "pin",
    "otp",
    "password",
    "ssn",
}

# Regex to detect potential account numbers or Indian ID numbers (like 12-digit Aadhaar or 10-char PAN or 9-18 digit account numbers)
SENSITIVE_PATTERNS = [
    re.compile(r"\b\d{9,18}\b"),  # 9-18 digit account/card numbers
    re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"),  # Aadhaar format
    re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE),  # PAN format
]


def sanitize_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitizes caller facts to strictly enforce Financial Services privacy rules.
    
    Hard Rule: Do not store account or ID numbers, cards, OTP, PIN, or passwords.
    Allowed: Schemes already checked, eligibility answers, preferences.
    """
    if not isinstance(facts, dict):
        return {}

    sanitized = {}
    for key, value in facts.items():
        k_lower = str(key).lower().strip()
        
        # Check if key name is prohibited
        if any(prohibited in k_lower for prohibited in PROHIBITED_KEYS):
            logger.warning(f"Privacy guardrail: Refused to store sensitive key '{key}'.")
            continue

        val_str = str(value)
        # Check if value matches sensitive data patterns (e.g. account numbers, Aadhaar, PAN)
        has_sensitive_data = any(pattern.search(val_str) for pattern in SENSITIVE_PATTERNS)
        if has_sensitive_data:
            logger.warning(f"Privacy guardrail: Refused to store sensitive value in key '{key}'.")
            continue

        sanitized[key] = value

    return sanitized


def sanitize_text(text: Optional[str]) -> str:
    """Sanitizes freeform text to ensure no sensitive financial numbers or credentials are saved.
    
    Replaces card/account numbers, Aadhaar, PAN, OTP, PIN, passwords with [REDACTED].
    """
    if not text:
        return ""
    clean = str(text)
    for pattern in SENSITIVE_PATTERNS:
        clean = pattern.sub("[REDACTED_SENSITIVE_DATA]", clean)
    # Redact common credential terms if followed by numbers
    clean = re.sub(r"(?i)\b(otp|pin|cvv|password)\s*[:=]?\s*\d+", r"\1 [REDACTED]", clean)
    return clean.strip()


def generate_escalation_id() -> str:
    """Generates a unique human-readable reference ID in the format ESC-XXXXXX."""
    import secrets
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    suffix = "".join(secrets.choice(chars) for _ in range(6))
    return f"ESC-{suffix}"


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Returns a connection to the SQLite database."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes the database tables for callers, escalations, and call analytics if they do not exist."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = get_connection(target_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS callers (
                    user_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    language_preference TEXT DEFAULT 'en-IN',
                    facts TEXT DEFAULT '{}',
                    last_interaction TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_callers_name ON callers(name COLLATE NOCASE)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS escalations (
                    reference_id TEXT PRIMARY KEY,
                    caller_name TEXT NOT NULL,
                    user_id TEXT,
                    issue_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    already_checked TEXT,
                    urgency TEXT NOT NULL,
                    caller_language TEXT DEFAULT 'en-IN',
                    follow_up_method TEXT DEFAULT 'phone',
                    status TEXT DEFAULT 'OPEN',
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_escalations_status ON escalations(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_escalations_caller_name ON escalations(caller_name COLLATE NOCASE)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS call_analytics (
                    call_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    outcome TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_call_analytics_outcome ON call_analytics(outcome)"
            )
        logger.info(f"Database initialized at {target_path}")
    finally:
        conn.close()


def get_caller(query: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Looks up a caller by user_id or name (case-insensitive).
    
    Returns the caller record formatted as:
    {
        "user_id": str,
        "name": str,
        "language_preference": str,
        "facts": dict,
        "last_interaction": str (ISO timestamp)
    }
    """
    if not query or not query.strip():
        return None

    clean_query = query.strip()
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = get_connection(target_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, name, language_preference, facts, last_interaction
            FROM callers
            WHERE user_id = ? OR name LIKE ? COLLATE NOCASE
            ORDER BY last_interaction DESC
            LIMIT 1
            """,
            (clean_query, f"%{clean_query}%"),
        )
        row = cursor.fetchone()
        if not row:
            return None

        try:
            facts_dict = json.loads(row["facts"])
        except Exception:
            facts_dict = {}

        return {
            "user_id": row["user_id"],
            "name": row["name"],
            "language_preference": row["language_preference"],
            "facts": facts_dict,
            "last_interaction": row["last_interaction"],
        }
    finally:
        conn.close()


def save_caller(
    name: str,
    language_preference: str = "en-IN",
    facts: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Saves or updates a caller record.
    
    Enforces privacy sanitization on facts and records the current timestamp.
    """
    if not name or not name.strip():
        raise ValueError("Caller name is required to save record.")

    clean_name = name.strip()
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    existing = get_caller(user_id or clean_name, db_path=target_path)
    if existing:
        final_user_id = existing["user_id"]
        merged_facts = existing.get("facts", {})
        if facts:
            merged_facts.update(facts)
        clean_facts = sanitize_facts(merged_facts)
    else:
        if not user_id:
            normalized_name = re.sub(r"[^a-zA-Z0-9]", "_", clean_name.lower())
            final_user_id = f"user_{normalized_name}"
        else:
            final_user_id = user_id.strip()
        clean_facts = sanitize_facts(facts or {})

    last_interaction = datetime.now(timezone.utc).isoformat()
    facts_json = json.dumps(clean_facts)

    conn = get_connection(target_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO callers (user_id, name, language_preference, facts, last_interaction)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name=excluded.name,
                    language_preference=excluded.language_preference,
                    facts=excluded.facts,
                    last_interaction=excluded.last_interaction
                """,
                (final_user_id, clean_name, language_preference, facts_json, last_interaction),
            )
    finally:
        conn.close()

    record = {
        "user_id": final_user_id,
        "name": clean_name,
        "language_preference": language_preference,
        "facts": clean_facts,
        "last_interaction": last_interaction,
    }
    logger.info(f"Saved caller record: {record}")
    return record


def save_escalation(
    caller_name: str,
    issue_type: str,
    summary: str,
    already_checked: str,
    urgency: str = "HIGH",
    caller_language: str = "en-IN",
    follow_up_method: str = "phone",
    user_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Saves a new human-in-the-loop escalation ticket with privacy sanitization.
    
    Hard Rules:
    - Never store passwords, OTPs, PINs, card numbers, or bank account numbers.
    - Status is always initialized to 'OPEN'.
    - Reference ID is generated in format ESC-XXXXXX.
    """
    if not caller_name or not caller_name.strip():
        raise ValueError("Caller name is required to create an escalation ticket.")

    clean_caller_name = caller_name.strip()
    clean_summary = sanitize_text(summary)
    clean_already_checked = sanitize_text(already_checked)
    clean_issue_type = issue_type.strip() if issue_type else "GENERAL_ESCALATION"
    clean_urgency = urgency.strip().upper() if urgency else "HIGH"
    clean_language = caller_language.strip() if caller_language else "en-IN"
    clean_follow_up = follow_up_method.strip() if follow_up_method else "phone"

    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = get_connection(target_path)
    
    # Generate a unique reference ID
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with conn:
            cursor = conn.cursor()
            # Ensure unique ID
            for _ in range(10):
                ref_id = generate_escalation_id()
                cursor.execute("SELECT 1 FROM escalations WHERE reference_id = ?", (ref_id,))
                if not cursor.fetchone():
                    break
            else:
                import uuid
                ref_id = f"ESC-{uuid.uuid4().hex[:6].upper()}"

            cursor.execute(
                """
                INSERT INTO escalations (
                    reference_id, caller_name, user_id, issue_type, summary,
                    already_checked, urgency, caller_language, follow_up_method,
                    status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ref_id,
                    clean_caller_name,
                    user_id,
                    clean_issue_type,
                    clean_summary,
                    clean_already_checked,
                    clean_urgency,
                    clean_language,
                    clean_follow_up,
                    "OPEN",
                    created_at,
                ),
            )
    finally:
        conn.close()

    escalation_record = {
        "reference_id": ref_id,
        "caller_name": clean_caller_name,
        "user_id": user_id,
        "issue_type": clean_issue_type,
        "summary": clean_summary,
        "already_checked": clean_already_checked,
        "urgency": clean_urgency,
        "caller_language": clean_language,
        "follow_up_method": clean_follow_up,
        "status": "OPEN",
        "created_at": created_at,
    }
    logger.info(f"Created escalation record: {escalation_record}")
    return escalation_record


def get_escalation(reference_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves an escalation record by its reference ID."""
    if not reference_id or not reference_id.strip():
        return None

    clean_id = reference_id.strip()
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = get_connection(target_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT reference_id, caller_name, user_id, issue_type, summary,
                   already_checked, urgency, caller_language, follow_up_method,
                   status, created_at
            FROM escalations
            WHERE reference_id = ?
            """,
            (clean_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def list_escalations(status: Optional[str] = None, db_path: Optional[str] = None) -> list[Dict[str, Any]]:
    """Lists escalations, optionally filtered by status (e.g. 'OPEN')."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = get_connection(target_path)
    try:
        cursor = conn.cursor()
        if status:
            cursor.execute(
                """
                SELECT reference_id, caller_name, user_id, issue_type, summary,
                       already_checked, urgency, caller_language, follow_up_method,
                       status, created_at
                FROM escalations
                WHERE status = ?
                ORDER BY created_at DESC
                """,
                (status.strip(),),
            )
        else:
            cursor.execute(
                """
                SELECT reference_id, caller_name, user_id, issue_type, summary,
                       already_checked, urgency, caller_language, follow_up_method,
                       status, created_at
                FROM escalations
                ORDER BY created_at DESC
                """
            )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def save_call_analytics(
    call_id: str,
    channel: str,
    outcome: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Saves or updates a call analytics record."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    timestamp = datetime.now(timezone.utc).isoformat()

    conn = get_connection(target_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO call_analytics (call_id, timestamp, channel, outcome)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(call_id) DO UPDATE SET
                    channel=excluded.channel,
                    outcome=excluded.outcome,
                    timestamp=excluded.timestamp
                """,
                (call_id, timestamp, channel, outcome),
            )
    finally:
        conn.close()

    return {
        "call_id": call_id,
        "timestamp": timestamp,
        "channel": channel,
        "outcome": outcome,
    }


def get_call_metrics(db_path: Optional[str] = None) -> Dict[str, int]:
    """Retrieves aggregated metrics: total calls, successful calls, and failed calls."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = get_connection(target_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM call_analytics")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM call_analytics WHERE outcome = 'SUCCESS'")
        success = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM call_analytics WHERE outcome = 'FAILED'")
        failed = cursor.fetchone()[0]

        return {
            "total_calls": total,
            "successful_calls": success,
            "failed_calls": failed,
        }
    finally:
        conn.close()


def get_recent_calls(limit: int = 50, db_path: Optional[str] = None) -> list[Dict[str, Any]]:
    """Retrieves recent call logs."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = get_connection(target_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT call_id, timestamp, channel, outcome
            FROM call_analytics
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# Initialize default DB on import
init_db()


