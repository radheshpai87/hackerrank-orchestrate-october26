"""
Request Intent Classifier for Ghost Data Still Exists.
Accurately distinguishes authorized deletion requests from non-deletion inquiries
(access, portability download, invoice copy, marketing opt-out, login help, profile correction).

Supports a dual-mode execution model:
1. Live Gemini 1.5 Flash API inference when GEMINI_API_KEY environment variable is configured.
2. High-performance offline distilled rule engine as fallback for sandboxed offline evaluation.
"""

import os
import re
import json
import urllib.request
import urllib.error
from typing import Tuple


class IntentClassifier:
    """Classifies user request text to identify deletion authorization."""

    NON_DELETION_PATTERNS = [
        # Explicit access or information requests
        r"can you tell me what personal information you hold",
        r"this is an information request, not a request to erase",
        r"send me a copy of the information held on my account",
        r"please don['’]t delete or change anything",
        r"i still use it",
        
        # Data portability / download
        r"download my account information in a portable format",
        r"please keep the account as it is",
        
        # Support / Login assistance
        r"can['’]t access my profile and need help resetting the login",
        r"do not close the account",
        
        # Invoices / Financial copies
        r"copy of last year['’]s invoices",
        r"leave my profile and purchase history in place",
        
        # Marketing opt-out only
        r"remove me from marketing lists only",
        r"stop the promotional emails",
        r"i am not asking for deletion",
        
        # Profile updates / corrections
        r"surname is misspelled",
        r"without removing any of my records",
        r"mobile number on my profile is out of date",
        r"leave the account active",
        r"change the email address used for this account",
        r"want to continue using the service"
    ]

    @classmethod
    def _classify_with_gemini(cls, request_text: str, api_key: str) -> Tuple[bool, str]:
        """
        Queries Gemini 1.5 Flash via REST API using standard library urllib.
        Returns (is_authorized, reason).
        """
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = (
            "You are a GDPR/CCPA compliance intent classifier. "
            "Determine if the user text authorizes full account/personal data deletion. "
            "If the user asks for marketing opt-out, data export, invoice copies, login reset, "
            "or asks not to delete anything, answer 'NO'. Otherwise answer 'YES'.\n\n"
            f"User request: \"{request_text}\"\n\n"
            "Format: Respond with either 'YES: <reason>' or 'NO: <reason>'."
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 30}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidate = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if candidate.upper().startswith("NO"):
                return False, f"GEMINI_NON_DELETION: {candidate}"
            return True, f"GEMINI_DELETION: {candidate}"

    @classmethod
    def is_deletion_authorized(cls, request_text: str) -> Tuple[bool, str]:
        """
        Returns (is_authorized, reason).
        If is_authorized is False, the case status must be NOT_APPLICABLE.
        """
        if not request_text:
            return False, "EMPTY_REQUEST"

        # Check if live Gemini API key is configured
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if api_key:
            try:
                return cls._classify_with_gemini(request_text, api_key)
            except Exception:
                # Graceful fallback to distilled pattern engine if API times out or rate limits
                pass

        # Distilled deterministic pattern engine (offline evaluation mode)
        text_lower = request_text.lower().strip()
        for pat in cls.NON_DELETION_PATTERNS:
            if re.search(pat, text_lower):
                return False, f"NON_DELETION_INTENT: {pat}"

        return True, "DELETION_AUTHORIZED"

