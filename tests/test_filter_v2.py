"""Filter v2 regression tests (specs.md s.4 amendment 2026-10-23).

Fixtures are the six REAL postings v1 queued on its first catch-up cycle -
all noise - plus positive controls that must keep passing.
"""

import pytest
from jobcatcher.fetch import Posting
from jobcatcher.filter import filter_posting


def mk(title, location=None, description=None):
    return Posting(company="X", platform="greenhouse", slug="x", job_id="1",
                   title=title, url="https://example.com/1", location=location,
                   description_text=description)


# --- the six v1 noise items: every one must now die ---
NOISE = [
    ("Stripe", "Head of AI Startups, EMEA", "Dublin, London, Paris, Berlin, Stockholm"),
    ("Groww", "SDE - II (Credit - Android)", "Bengaluru-VTP, India"),
    ("Sarvam AI", "Marketing internship (brand & communication)", "Bengaluru"),
    ("Thoughtworks", "Executive Assistant", "New York City, New York, USA"),
    ("Twilio", "Software Development Engineer", "Remote - Ireland"),
    ("InMobi", "Intern - Creative & Communications, People Team", "Bangalore"),
]


@pytest.mark.parametrize("company,title,location", NOISE)
def test_v1_noise_now_killed(company, title, location):
    r = filter_posting(mk(title, location))
    assert not r.passed, f"{company}: {title} should be killed"
    assert r.reason


def test_noise_kill_reasons_are_the_right_gates():
    assert "Seniority" in (filter_posting(mk(NOISE[0][1], NOISE[0][2])).reason or "")
    assert "Level marker" in (filter_posting(mk(NOISE[1][1], NOISE[1][2])).reason or "")
    assert "role-family" in (filter_posting(mk(NOISE[2][1], NOISE[2][2])).reason or "")
    assert "Location" in (filter_posting(mk(NOISE[4][1], NOISE[4][2])).reason or "")


# --- positive controls: genuine fresher-scope postings must pass ---
GOOD = [
    ("Software Engineer Intern", "Bengaluru, Karnataka, India"),
    ("Software Development Engineer (Fresher)", "Remote - India"),
    ("Data Analyst", "Mumbai, India"),
    ("Machine Learning Intern", "Bengaluru"),
    ("QA Engineer - Entry Level", None),
    ("Backend Developer", "Remote"),
    ("Full Stack Developer Intern", "Hyderabad, India"),
    ("Data Science Intern", "Remote - India"),
    ("Associate Software Engineer", "Pune, India"),
    ("AI Engineer", "Bengaluru, India"),
]


@pytest.mark.parametrize("title,location", GOOD)
def test_fresher_scope_passes(title, location):
    r = filter_posting(mk(title, location))
    assert r.passed, f"{title} should pass, killed by: {r.reason}"


def test_business_development_dies():
    r = filter_posting(mk("Business Development Executive", "Bengaluru, India"))
    assert not r.passed


def test_remote_no_country_passes_but_remote_foreign_dies():
    assert filter_posting(mk("Software Engineer", "Remote")).passed
    assert not filter_posting(mk("Software Engineer", "Remote - Germany")).passed
