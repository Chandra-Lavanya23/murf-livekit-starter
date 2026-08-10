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


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Returns a connection to the SQLite database."""
    target_path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes the database table for callers if it does not exist."""
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


# Initialize default DB on import
init_db()
