"""Platform fetchers and normalization for Greenhouse, Ashby, and Lever."""

from dataclasses import dataclass
import datetime as dt
import html
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, Union

from .catalog import Board

logger = logging.getLogger(__name__)

USER_AGENT = "JobCatcher/1.0 (urllib; ATS watcher)"
DEFAULT_TIMEOUT = 20.0


@dataclass
class Posting:
    """Normalized representation of a job posting."""
    company: str
    platform: str
    slug: str
    job_id: str
    title: str
    url: str
    location: Optional[str] = None
    posted_at: Optional[str] = None
    compensation: Optional[Union[Dict[str, Any], str]] = None
    description_text: Optional[str] = None


@dataclass
class FetchResult:
    """Result of fetching a single board."""
    board: Board
    postings: List[Posting]
    error: Optional[str] = None
    status_code: Optional[int] = None
    is_success: bool = True


def clean_html(raw: Optional[str], max_len: int = 6000) -> Optional[str]:
    """Convert HTML or plain text to cleaned plain text, truncated to max_len chars."""
    if not raw:
        return None
    # Replace block-level elements and breaks with newlines
    text = re.sub(r'</?(?:br|p|div|li|h[1-6]|tr)[^>]*>', '\n', raw, flags=re.IGNORECASE)
    # Strip all other HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    # Normalize horizontal whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    # Normalize consecutive newlines and trim line boundaries
    text = re.sub(r'[ \t]*\n+[ \t]*', '\n', text).strip()
    if not text:
        return None
    if len(text) > max_len:
        text = text[:max_len]
    return text


def _ashby_location(job: dict) -> Optional[str]:
    for key in ("locationName", "location"):
        v = job.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict) and v.get("name"):
            return str(v["name"]).strip()
    # Address fallback
    addr = job.get("address")
    if isinstance(addr, dict):
        postal = addr.get("postalAddress")
        if isinstance(postal, dict):
            loc = postal.get("addressLocality")
            if loc:
                return str(loc).strip()
    return None


def _ashby_compensation(job: dict) -> Optional[Union[dict, str]]:
    comp = job.get("compensation")
    if not comp:
        return None
    if isinstance(comp, dict):
        # Check if it has any meaningful content
        if (
            comp.get("compensationTierSummary")
            or comp.get("scrapeableCompensationSalarySummary")
            or comp.get("compensationTiers")
            or comp.get("summaryComponents")
        ):
            return comp
        # Check if dictionary has any non-empty values
        if any(v for v in comp.values() if v is not None and v != "" and v != []):
            return comp
        return None
    if isinstance(comp, str) and comp.strip():
        return comp.strip()
    return None


def parse_greenhouse_payload(data: dict, board: Board) -> List[Posting]:
    postings: List[Posting] = []
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        job_id = str(j.get("id")) if j.get("id") is not None else ""
        if not job_id:
            continue
        title = (j.get("title") or "").strip()
        url = j.get("absolute_url") or f"https://boards.greenhouse.io/{board.slug}/jobs/{job_id}"
        
        loc = j.get("location")
        loc_str = None
        if isinstance(loc, dict):
            loc_str = loc.get("name")
        elif isinstance(loc, str):
            loc_str = loc
        if loc_str:
            loc_str = loc_str.strip()

        posted = j.get("updated_at") or j.get("first_published") or j.get("created_at")
        desc = clean_html(j.get("content") or j.get("description") or j.get("notes"))

        postings.append(Posting(
            company=board.company,
            platform="greenhouse",
            slug=board.slug,
            job_id=job_id,
            title=title,
            url=url,
            location=loc_str,
            posted_at=posted,
            compensation=None,
            description_text=desc,
        ))
    return postings


def parse_ashby_payload(data: dict, board: Board) -> List[Posting]:
    postings: List[Posting] = []
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        job_id = str(j.get("id")) if j.get("id") is not None else ""
        if not job_id:
            continue
        title = (j.get("title") or "").strip()
        url = j.get("jobUrl") or j.get("applyUrl") or f"https://jobs.ashbyhq.com/{board.slug}/{job_id}"
        loc_str = _ashby_location(j)
        posted = j.get("publishedAt")
        comp = _ashby_compensation(j)
        desc = clean_html(j.get("descriptionPlain") or j.get("descriptionHtml") or j.get("description"))

        postings.append(Posting(
            company=board.company,
            platform="ashby",
            slug=board.slug,
            job_id=job_id,
            title=title,
            url=url,
            location=loc_str,
            posted_at=posted,
            compensation=comp,
            description_text=desc,
        ))
    return postings


def parse_lever_payload(data: Union[list, dict], board: Board) -> List[Posting]:
    postings: List[Posting] = []
    jobs = data if isinstance(data, list) else data.get("postings", []) if isinstance(data, dict) else []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        job_id = str(j.get("id")) if j.get("id") is not None else ""
        if not job_id:
            continue
        title = (j.get("text") or "").strip()
        url = j.get("hostedUrl") or j.get("applyUrl") or f"https://jobs.lever.co/{board.slug}/{job_id}"
        
        cats = j.get("categories") or {}
        loc_str = cats.get("location") if isinstance(cats, dict) else None
        if loc_str:
            loc_str = str(loc_str).strip()

        created = j.get("createdAt")
        posted = None
        if isinstance(created, (int, float)):
            try:
                posted = dt.datetime.fromtimestamp(created / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                posted = str(created)
        elif isinstance(created, str):
            posted = created

        desc = clean_html(j.get("descriptionPlain") or j.get("description"))

        postings.append(Posting(
            company=board.company,
            platform="lever",
            slug=board.slug,
            job_id=job_id,
            title=title,
            url=url,
            location=loc_str,
            posted_at=posted,
            compensation=None,
            description_text=desc,
        ))
    return postings


def get_board_url(board: Board) -> str:
    slug_enc = urllib.parse.quote(board.slug)
    if board.platform == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{slug_enc}/jobs"
    elif board.platform == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{slug_enc}?includeCompensation=true"
    elif board.platform == "lever":
        return f"https://api.lever.co/v0/postings/{slug_enc}?mode=json"
    else:
        raise ValueError(f"Unsupported platform: {board.platform}")


def fetch_board(
    board: Board,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Optional[Any] = None,
) -> FetchResult:
    """
    Fetch a board using urllib. Failures return an error record, never raise out of cycle.
    """
    try:
        url = get_board_url(board)
    except ValueError as e:
        return FetchResult(board=board, postings=[], error=str(e), is_success=False)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )

    try:
        if opener is not None:
            resp = opener.open(req, timeout=timeout)
        else:
            resp = urllib.request.urlopen(req, timeout=timeout)

        with resp:
            code = getattr(resp, "status", getattr(resp, "code", 200))
            raw_body = resp.read()
            body_text = raw_body.decode("utf-8", "replace")
            data = json.loads(body_text)

        if board.platform == "greenhouse":
            postings = parse_greenhouse_payload(data, board)
        elif board.platform == "ashby":
            postings = parse_ashby_payload(data, board)
        elif board.platform == "lever":
            postings = parse_lever_payload(data, board)
        else:
            postings = []

        return FetchResult(board=board, postings=postings, error=None, status_code=code, is_success=True)

    except urllib.error.HTTPError as e:
        logger.info("Board HTTP error for %s (%s): %s %s", board.company, board.slug, e.code, e.reason)
        return FetchResult(
            board=board,
            postings=[],
            error=f"HTTP {e.code}: {e.reason}",
            status_code=e.code,
            is_success=False,
        )
    except Exception as e:
        logger.info("Board fetch failed for %s (%s): %s", board.company, board.slug, e)
        return FetchResult(
            board=board,
            postings=[],
            error=str(e),
            status_code=None,
            is_success=False,
        )
