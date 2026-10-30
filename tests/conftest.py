"""Shared test fixtures for job-catcher tests."""

import json
import pytest

# Fixture payload shaped like Greenhouse public API
GREENHOUSE_FIXTURE = {
    "jobs": [
        {
            "id": 8172487,
            "title": "Software Engineer, Backend",
            "company_name": "Stripe",
            "absolute_url": "https://stripe.com/jobs/search?gh_jid=8172487",
            "location": {"name": "Bengaluru, India"},
            "updated_at": "2026-10-21T12:00:00Z",
            "content": "<p>We are looking for a Software Engineer to join our payments team.</p>",
        },
        {
            "id": 8172488,
            "title": "Senior Infrastructure Engineer",
            "company_name": "Stripe",
            "absolute_url": "https://stripe.com/jobs/search?gh_jid=8172488",
            "location": {"name": "Remote, India"},
            "updated_at": "2026-10-22T08:30:00Z",
            "content": "<p>Requires 5+ years of experience in distributed systems.</p>",
        },
    ],
    "meta": {"total": 2},
}

# Fixture payload shaped like Ashby public API with includeCompensation=true
ASHBY_FIXTURE = {
    "apiVersion": "2023-05-01",
    "jobs": [
        {
            "id": "e89b21a3-4567-4890-a123-abcdef012345",
            "title": "Machine Learning Engineer (Early Career)",
            "jobUrl": "https://jobs.ashbyhq.com/replicate/e89b21a3-4567-4890-a123-abcdef012345",
            "locationName": "San Francisco, CA / Remote",
            "publishedAt": "2026-10-20T15:00:00.000Z",
            "descriptionPlain": "Build scalable ML training pipelines. Fresh graduates from 2026/2027 are welcome to apply.",
            "compensation": {
                "compensationTierSummary": "$140,000 - $180,000 USD",
                "scrapeableCompensationSalarySummary": "$140,000 - $180,000",
                "summaryComponents": [{"type": "salary", "minValue": 140000, "maxValue": 180000, "currency": "USD"}],
            },
        },
        {
            "id": "f90c32b4-5678-4901-b234-bcdef0123456",
            "title": "Principal Architect",
            "jobUrl": "https://jobs.ashbyhq.com/replicate/f90c32b4-5678-4901-b234-bcdef0123456",
            "locationName": "New York, NY",
            "publishedAt": "2026-10-19T10:00:00.000Z",
            "descriptionPlain": "10+ years experience required.",
            "compensation": None,
        },
    ],
}

# Fixture payload shaped like Lever public API
LEVER_FIXTURE = [
    {
        "id": "789abcde-0123-4567-890a-bcdef0123456",
        "text": "Data Analyst Intern",
        "hostedUrl": "https://jobs.lever.co/cred/789abcde-0123-4567-890a-bcdef0123456",
        "categories": {
            "commitment": "Internship",
            "department": "Analytics",
            "location": "Bengaluru",
            "team": "Data",
        },
        "createdAt": 1792627200000,
        "descriptionPlain": "Exciting internship for students in data analysis and SQL.",
    },
    {
        "id": "890bcdef-1234-5678-90ab-cdef01234567",
        "text": "Director of Engineering",
        "hostedUrl": "https://jobs.lever.co/cred/890bcdef-1234-5678-90ab-cdef01234567",
        "categories": {
            "commitment": "Full-time",
            "department": "Engineering",
            "location": "Bengaluru",
            "team": "Leadership",
        },
        "createdAt": 1792540800000,
        "descriptionPlain": "Lead multiple engineering teams.",
    },
]


@pytest.fixture
def greenhouse_payload():
    return json.loads(json.dumps(GREENHOUSE_FIXTURE))


@pytest.fixture
def ashby_payload():
    return json.loads(json.dumps(ASHBY_FIXTURE))


@pytest.fixture
def lever_payload():
    return json.loads(json.dumps(LEVER_FIXTURE))
