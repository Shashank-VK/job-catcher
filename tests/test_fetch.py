"""Tests for platform fetchers and normalization (catch-002)."""

import io
import json
import urllib.error
import pytest

from jobcatcher.catalog import Board
from jobcatcher.fetch import (
    clean_html,
    fetch_board,
    parse_ashby_payload,
    parse_greenhouse_payload,
    parse_lever_payload,
)


def test_greenhouse_normalization(greenhouse_payload):
    """catch-002: Unit: Greenhouse recorded-shape fixture -> normalized fields asserted."""
    board = Board(company="Stripe", platform="greenhouse", slug="stripe")
    postings = parse_greenhouse_payload(greenhouse_payload, board)

    assert len(postings) == 2
    p1 = postings[0]
    assert p1.company == "Stripe"
    assert p1.platform == "greenhouse"
    assert p1.slug == "stripe"
    assert p1.job_id == "8172487"
    assert p1.title == "Software Engineer, Backend"
    assert p1.url == "https://stripe.com/jobs/search?gh_jid=8172487"
    assert p1.location == "Bengaluru, India"
    assert p1.posted_at == "2026-10-21T12:00:00Z"
    assert p1.compensation is None
    assert p1.description_text == "We are looking for a Software Engineer to join our payments team."


def test_ashby_normalization(ashby_payload):
    """catch-002: Unit: Ashby recorded-shape fixture -> normalized fields asserted."""
    board = Board(company="Replicate", platform="ashby", slug="replicate")
    postings = parse_ashby_payload(ashby_payload, board)

    assert len(postings) == 2
    p1 = postings[0]
    assert p1.company == "Replicate"
    assert p1.platform == "ashby"
    assert p1.slug == "replicate"
    assert p1.job_id == "e89b21a3-4567-4890-a123-abcdef012345"
    assert p1.title == "Machine Learning Engineer (Early Career)"
    assert p1.url == "https://jobs.ashbyhq.com/replicate/e89b21a3-4567-4890-a123-abcdef012345"
    assert p1.location == "San Francisco, CA / Remote"
    assert p1.posted_at == "2026-10-20T15:00:00.000Z"
    assert isinstance(p1.compensation, dict)
    assert p1.compensation["compensationTierSummary"] == "$140,000 - $180,000 USD"
    assert "Fresh graduates from 2026/2027" in (p1.description_text or "")


def test_lever_normalization(lever_payload):
    """catch-002: Unit: Lever recorded-shape fixture -> normalized fields asserted."""
    board = Board(company="CRED", platform="lever", slug="cred")
    postings = parse_lever_payload(lever_payload, board)

    assert len(postings) == 2
    p1 = postings[0]
    assert p1.company == "CRED"
    assert p1.platform == "lever"
    assert p1.slug == "cred"
    assert p1.job_id == "789abcde-0123-4567-890a-bcdef0123456"
    assert p1.title == "Data Analyst Intern"
    assert p1.url == "https://jobs.lever.co/cred/789abcde-0123-4567-890a-bcdef0123456"
    assert p1.location == "Bengaluru"
    assert p1.posted_at is not None
    assert p1.compensation is None
    assert "Exciting internship" in (p1.description_text or "")


class FakeHTTPResponse:
    def __init__(self, data: bytes, status: int = 200):
        self._fp = io.BytesIO(data)
        self.status = status
        self.code = status

    def read(self, *args):
        return self._fp.read(*args)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class FakeOpener:
    def __init__(self, handler):
        self.handler = handler

    def open(self, req, timeout=20.0):
        return self.handler(req, timeout)


def test_http_error_404_recorded_never_raises():
    """catch-002: Unit: HTTP error / 404 -> board failure recorded, cycle continues."""
    board = Board(company="UnknownCo", platform="greenhouse", slug="unverified-404-slug")

    def raise_404(req, timeout):
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b"Not Found"),
        )

    opener = FakeOpener(raise_404)
    result = fetch_board(board, opener=opener)

    assert not result.is_success
    assert result.status_code == 404
    assert result.error == "HTTP 404: Not Found"
    assert len(result.postings) == 0


def test_fetch_success_with_fake_opener(greenhouse_payload):
    """Test successful board fetch with fake opener."""
    board = Board(company="Stripe", platform="greenhouse", slug="stripe")
    body = json.dumps(greenhouse_payload).encode("utf-8")

    def return_200(req, timeout):
        return FakeHTTPResponse(body, status=200)

    opener = FakeOpener(return_200)
    result = fetch_board(board, opener=opener)

    assert result.is_success
    assert result.status_code == 200
    assert result.error is None
    assert len(result.postings) == 2


def test_clean_html_truncation():
    """Test HTML stripping and truncation to 6000 chars."""
    raw = "<p>Hello <b>World</b>!</p><br><div>Some text</div>"
    assert clean_html(raw) == "Hello World!\nSome text"

    long_text = "a" * 8000
    cleaned = clean_html(long_text)
    assert len(cleaned) == 6000
