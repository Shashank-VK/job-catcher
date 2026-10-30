"""Tests for deterministic fresher filter (catch-004)."""

import pytest

from jobcatcher.fetch import Posting
from jobcatcher.filter import filter_posting


def make_posting(title: str, description: str = "") -> Posting:
    return Posting(
        company="Acme Corp",
        platform="greenhouse",
        slug="acme",
        job_id="test-1",
        title=title,
        url="https://example.com/job/1",
        description_text=description,
    )


def test_senior_software_engineer_killed_and_software_engineer_passes():
    """catch-004: Unit: 'Senior Software Engineer' killed; 'Software Engineer' passes."""
    p_senior = make_posting("Senior Software Engineer")
    res_senior = filter_posting(p_senior)
    assert not res_senior.passed
    assert "Seniority word 'Senior'" in (res_senior.reason or "")

    p_swe = make_posting("Software Engineer")
    res_swe = filter_posting(p_swe)
    assert res_swe.passed
    assert res_swe.reason is None


def test_years_experience_kill_and_pass():
    """catch-004: Unit: '3+ years experience' killed; '0-2 years' passes; 'Intern' passes."""
    # 3+ years experience in description -> killed
    p_exp3 = make_posting("Software Engineer", "Must have 3+ years experience in Python.")
    res_exp3 = filter_posting(p_exp3)
    assert not res_exp3.passed
    assert "3+ years" in (res_exp3.reason or "")

    # 0-2 years -> passes
    p_exp02 = make_posting("Junior Developer", "Looking for candidates with 0-2 years experience.")
    res_exp02 = filter_posting(p_exp02)
    assert res_exp02.passed
    assert res_exp02.reason is None

    # Intern -> passes
    p_intern = make_posting("Software Engineering Intern", "Current students or recent grads.")
    res_intern = filter_posting(p_intern)
    assert res_intern.passed
    assert res_intern.reason is None


def test_seniority_title_exclusions():
    """Test all explicitly excluded seniority titles."""
    for title in [
        "Staff Software Engineer",
        "Principal Machine Learning Scientist",
        "Lead Backend Engineer",
        "Engineering Manager",
        "Director of Engineering",
        "Sr. Frontend Engineer",
    ]:
        p = make_posting(title)
        res = filter_posting(p)
        assert not res.passed, f"Expected '{title}' to be killed"


def test_experience_variations():
    """Test variations of experience requirements."""
    # 5+ years -> killed
    assert not filter_posting(make_posting("Developer", "Requires 5+ years.")).passed
    # 3 - 5 years -> killed
    assert not filter_posting(make_posting("Developer", "Requires 3-5 years experience.")).passed
    # at least 4 years -> killed
    assert not filter_posting(make_posting("Developer", "Minimum 4 years of experience.")).passed
    # 1 year -> passes
    assert filter_posting(make_posting("Developer", "1 year of experience preferred.")).passed


def test_freshers_and_batch_exclusions():
    """Test explicit no-freshers and batch exclusions."""
    # Explicit no freshers -> killed
    p_no_fresh = make_posting("Developer", "Notice: No freshers. Only experienced applicants.")
    assert not filter_posting(p_no_fresh).passed

    # Batch 2024 only -> excludes 2026/2027/2028 -> killed
    p_batch_2024 = make_posting("Graduate Analyst", "Eligible: batch of 2024 only.")
    assert not filter_posting(p_batch_2024).passed

    # Batch 2027 -> target batch allowed -> passes
    p_batch_2027 = make_posting("Graduate Analyst", "Eligible: batch of 2027 only.")
    assert filter_posting(p_batch_2027).passed


def test_pass_through_on_missing_signal():
    """Test pass-through when no signals are present."""
    p_plain = make_posting("Data Scientist", "Join our fast growing team to build models.")
    res = filter_posting(p_plain)
    assert res.passed
    assert res.reason is None


def test_sub3_range_with_experience_phrasing_passes():
    """FCAR round-2 regression: "1-3 years of experience" must PASS — the range
    minimum is < 3, and the upper bound must not re-match as a standalone demand."""
    from jobcatcher.filter import check_experience_requirement
    assert check_experience_requirement("Requires 1-3 years of experience") is None
    assert check_experience_requirement("2-4 years of experience preferred") is None
    # ...while a range whose minimum is >= 3 still kills, and a standalone
    # >= 3 demand elsewhere in the same text still kills.
    assert check_experience_requirement("3-5 years of experience") is not None
    assert check_experience_requirement("1-3 years of experience; 5 years of experience in payments") is not None
