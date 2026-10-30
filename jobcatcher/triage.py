"""OmniRoute LLM triage client with graceful degradation."""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional

from .fetch import Posting

logger = logging.getLogger(__name__)

DEFAULT_OMNIROUTE_URL = "http://localhost:20128/v1/chat/completions"
DEFAULT_MODEL = "gemini/gemini-3.1-flash-lite"
DEFAULT_KEY_PATH = Path.home() / ".config/omniroute-local/client_key"
TRIAGE_UNAVAILABLE = "triage_unavailable"

SYSTEM_PROMPT = """You are a job posting triage assistant. Your task is to extract signals from a job posting and decide whether to KEEP or KILL it.

Extract the following in strict JSON:
1. "role_family": One of "SWE", "backend", "full-stack", "data", "ML", "AI", "QA", or "other".
2. "location_remote": Location or remote/hybrid signal.
3. "batch_eligibility": Any batch or graduation year or experience eligibility signal (especially 2026, 2027, 2028, intern, trainee).
4. "pay_signal": Any compensation, salary, or stipend signal mentioned, or "not specified".
5. "verdict": "KEEP" or "KILL".
   - KEEP only if there is an intern/trainee/2027 signal OR an entry-level family match (SWE, backend, full-stack, data, ML, AI, QA).
   - Otherwise KILL.
6. "reason": Brief rationale for the verdict.

Return ONLY a valid JSON object with keys: "role_family", "location_remote", "batch_eligibility", "pay_signal", "verdict", "reason"."""


@dataclass
class TriageResult:
    """Result of LLM triage."""
    verdict: str  # "KEEP", "KILL", or "triage_unavailable"
    kept: bool    # True for KEEP and triage_unavailable; False for KILL
    role_family: Optional[str] = None
    location_remote: Optional[str] = None
    batch_eligibility: Optional[str] = None
    pay_signal: Optional[str] = None
    reason: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


def load_api_key(key_path: Optional[Path] = None) -> str:
    """Read API key from disk. Never hardcoded or printed."""
    p = key_path if key_path is not None else DEFAULT_KEY_PATH
    if not p.is_file():
        raise FileNotFoundError(f"Key file not found at {p}")
    key = p.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError("Key file is empty")
    return key


def _clean_json_content(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return content.strip()


class OmniRouteClient:
    """Client for OmniRoute chat completions with graceful degradation."""

    def __init__(
        self,
        endpoint: str = DEFAULT_OMNIROUTE_URL,
        model: str = DEFAULT_MODEL,
        key_path: Optional[Path] = None,
        timeout: float = 20.0,
        transport: Optional[Callable[[urllib.request.Request, float], dict]] = None,
    ):
        self.endpoint = endpoint
        self.model = model
        self.key_path = key_path
        self.timeout = timeout
        self.transport = transport

    def triage(self, posting: Posting) -> TriageResult:
        """
        Triage a posting. ANY failure results in verdict 'triage_unavailable' and kept=True.
        """
        try:
            return self._triage_inner(posting)
        except Exception as e:
            # Graceful degradation: never crash, never drop the posting
            # Do NOT log or print raw request/keys
            logger.warning("OmniRoute triage unavailable for %s (%s): %s", posting.company, posting.job_id, type(e).__name__)
            return TriageResult(
                verdict=TRIAGE_UNAVAILABLE,
                kept=True,
                reason=f"Triage unavailable ({type(e).__name__})",
            )

    def _triage_inner(self, posting: Posting) -> TriageResult:
        # Load key at runtime
        key = load_api_key(self.key_path)

        user_content = (
            f"Title: {posting.title}\n"
            f"Company: {posting.company}\n"
            f"Location: {posting.location or 'Not specified'}\n"
            f"Compensation: {posting.compensation or 'Not specified'}\n"
            f"Description:\n{posting.description_text or 'No description provided'}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        data_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self.endpoint,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "User-Agent": "JobCatcher/1.0",
            },
            method="POST",
        )

        if self.transport is not None:
            resp_dict = self.transport(req, self.timeout)
        else:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_body = resp.read().decode("utf-8", "replace")
                resp_dict = json.loads(raw_body)

        choices = resp_dict.get("choices", [])
        if not choices or not isinstance(choices, list):
            raise ValueError("No choices in completions response")

        message = choices[0].get("message", {})
        raw_content = message.get("content", "")
        cleaned = _clean_json_content(raw_content)
        parsed = json.loads(cleaned)

        raw_verdict = str(parsed.get("verdict", "")).strip().upper()
        if raw_verdict not in ("KEEP", "KILL"):
            raise ValueError(f"Invalid verdict from LLM: {raw_verdict}")

        kept = (raw_verdict == "KEEP")
        return TriageResult(
            verdict=raw_verdict,
            kept=kept,
            role_family=parsed.get("role_family"),
            location_remote=parsed.get("location_remote"),
            batch_eligibility=parsed.get("batch_eligibility"),
            pay_signal=parsed.get("pay_signal"),
            reason=parsed.get("reason"),
            raw_response=parsed,
        )


def triage_posting(
    posting: Posting,
    client: Optional[OmniRouteClient] = None,
) -> TriageResult:
    """Convenience helper to triage a posting using the given client or default client."""
    if client is None:
        client = OmniRouteClient()
    return client.triage(posting)
