"""Regtest (2026-10-24): a foreign city not on the original list must die."""
from jobcatcher.fetch import Posting
from jobcatcher.filter import filter_posting


def test_sao_paulo_location_killed():
    p = Posting(company="X", platform="greenhouse", slug="x", job_id="1",
                title="Full Stack Software Engineer", url="https://example.com/1",
                location="Sao Paulo")
    r = filter_posting(p)
    assert not r.passed and r.reason and "Location" in r.reason
