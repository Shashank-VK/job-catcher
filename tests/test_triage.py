"""Tests for OmniRoute LLM triage with graceful degradation (catch-005)."""

import json
from pathlib import Path
import urllib.error
import pytest

from jobcatcher.fetch import Posting
from jobcatcher.triage import (
    OmniRouteClient,
    TRIAGE_UNAVAILABLE,
    load_api_key,
    triage_posting,
)


def sample_posting() -> Posting:
    return Posting(
        company="Stripe",
        platform="greenhouse",
        slug="stripe",
        job_id="stripe-123",
        title="Software Engineer, Backend",
        url="https://stripe.com/jobs/123",
        location="Bengaluru, India",
        description_text="Join our core infrastructure team building scalable payments APIs.",
    )


def test_fake_transport_returning_keep_json(tmp_path: Path):
    """catch-005: Unit: fake transport returning KEEP JSON -> verdicts + signals parsed."""
    key_file = tmp_path / "client_key"
    key_file.write_text("secret_test_key_12345", encoding="utf-8")

    response_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "role_family": "SWE",
                        "location_remote": "Bengaluru, onsite/hybrid",
                        "batch_eligibility": "Open to freshers/2026/2027",
                        "pay_signal": "Competitive market standard",
                        "verdict": "KEEP",
                        "reason": "Entry-level SWE role matching criteria",
                    })
                }
            }
        ]
    }

    recorded_headers = {}

    def fake_transport(req, timeout):
        for k, v in req.headers.items():
            recorded_headers[k] = v
        return response_payload

    client = OmniRouteClient(
        key_path=key_file,
        transport=fake_transport,
    )

    p = sample_posting()
    result = client.triage(p)

    assert result.verdict == "KEEP"
    assert result.kept is True
    assert result.role_family == "SWE"
    assert result.location_remote == "Bengaluru, onsite/hybrid"
    assert result.batch_eligibility == "Open to freshers/2026/2027"
    assert result.pay_signal == "Competitive market standard"
    assert "Entry-level SWE" in (result.reason or "")

    # Assert auth header was set properly with key
    assert recorded_headers.get("Authorization") == "Bearer secret_test_key_12345"


def test_fake_transport_returning_kill_json(tmp_path: Path):
    """catch-005: Unit: fake transport returning KILL JSON -> verdicts + signals parsed."""
    key_file = tmp_path / "client_key"
    key_file.write_text("secret_test_key_12345", encoding="utf-8")

    response_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "role_family": "other",
                        "location_remote": "London, UK",
                        "batch_eligibility": "Mid-career only",
                        "pay_signal": "not specified",
                        "verdict": "KILL",
                        "reason": "Non-technical sales role outside scope",
                    })
                }
            }
        ]
    }

    client = OmniRouteClient(
        key_path=key_file,
        transport=lambda req, timeout: response_payload,
    )

    p = sample_posting()
    result = client.triage(p)

    assert result.verdict == "KILL"
    assert result.kept is False
    assert result.role_family == "other"


def test_transport_raising_timeout_returns_triage_unavailable_and_kept(tmp_path: Path):
    """catch-005: Unit: transport raising/timeout -> verdict triage_unavailable, posting kept."""
    key_file = tmp_path / "client_key"
    key_file.write_text("test_key", encoding="utf-8")

    def raising_transport(req, timeout):
        raise TimeoutError("Connection to OmniRoute timed out after 20s")

    client = OmniRouteClient(
        key_path=key_file,
        transport=raising_transport,
    )

    p = sample_posting()
    result = client.triage(p)

    assert result.verdict == TRIAGE_UNAVAILABLE
    assert result.kept is True
    assert "TimeoutError" in (result.reason or "")


def test_missing_key_file_returns_triage_unavailable_and_kept(tmp_path: Path):
    """Test graceful degradation when key file is missing."""
    nonexistent_key = tmp_path / "missing_key"
    client = OmniRouteClient(key_path=nonexistent_key)

    p = sample_posting()
    result = client.triage(p)

    assert result.verdict == TRIAGE_UNAVAILABLE
    assert result.kept is True


def test_malformed_json_response_returns_triage_unavailable_and_kept(tmp_path: Path):
    """Test graceful degradation when LLM returns non-JSON content."""
    key_file = tmp_path / "client_key"
    key_file.write_text("test_key", encoding="utf-8")

    client = OmniRouteClient(
        key_path=key_file,
        transport=lambda req, timeout: {"choices": [{"message": {"content": "This is not JSON"}}]},
    )

    p = sample_posting()
    result = client.triage(p)

    assert result.verdict == TRIAGE_UNAVAILABLE
    assert result.kept is True
