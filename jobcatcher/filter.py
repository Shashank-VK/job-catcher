"""Deterministic fresher filter per specs.md Section 4."""

from dataclasses import dataclass
import re
from typing import Optional

from .fetch import Posting


@dataclass
class FilterResult:
    """Result of running deterministic filter on a posting."""
    passed: bool
    reason: Optional[str] = None


# Seniority words to kill if present in the title
SENIORITY_TITLE_PATTERN = re.compile(
    r'\b(?:senior|sr\.?|staff|principal|lead|manager|director|vp|vice\s+president|head|chief|architect)\b',
    re.IGNORECASE,
)

# Level markers: SDE II / SDE-3 / L2 / standalone roman numerals II/III in a title.
# Fresher titles do not carry level markers; II/III always means mid-level here.
LEVEL_TITLE_PATTERN = re.compile(
    r'\b(?:ii|iii)\b|\b(?:sde|engineer|developer)\s*[- ]?\s*[23]\b|\bl[23]\b',
    re.IGNORECASE,
)

# Role-family gate (specs.md s.4 amendment 2026-10-23): the title must positively
# match one of his verified role families. A purely negative filter let a
# marketing internship, an executive-assistant post and a comms internship
# through on day one; C1 should never see those.
FAMILY_TITLE_PATTERN = re.compile(
    r'\b(?:engineer|engineering|developer|software|sde|swe|data|'
    r'machine\s+learning|ml|ai|qa|sdet|scientist|backend|back-end|full[\s-]?stack|'
    r'devops|analyst|programmer|test|testing|platform|systems?|cloud|android|ios|'
    r'web|api|automation|research)\b',
    re.IGNORECASE,
)

# Location gate (same amendment): an explicit foreign location with no India
# signal is queue noise for C1 (his doctrine: Karnataka on-site, or remote
# workable from India). Unstated / country-less "Remote" passes; C1 verifies.
INDIA_LOCATION_PATTERN = re.compile(
    r'\b(?:india|indian|bengaluru|bangalore|karnataka|hyderabad|pune|mumbai|'
    r'delhi|chennai|kolkata|gurgaon|gurugram|noida|ahmedabad|kochi|indore|'
    r'jaipur|coimbatore|mysuru|mangaluru|trivandrum|thiruvananthapuram)\b',
    re.IGNORECASE,
)
FOREIGN_LOCATION_PATTERN = re.compile(
    r'\b(?:ireland|dublin|london|paris|berlin|stockholm|munich|hamburg|amsterdam|'
    r'madrid|barcelona|lisbon|warsaw|prague|budapest|zurich|europe|emea|uk|'
    r'united\s+kingdom|germany|france|spain|netherlands|sweden|poland|'
    r'new\s+york|san\s+francisco|seattle|austin|boston|chicago|denver|toronto|'
    r'vancouver|canada|usa|united\s+states|u\.s\.a?\.|australia|sydney|'
    r'singapore|tokyo|dubai|uae|israel|tel\s+aviv|brazil|sao\s*paulo|mexico)\b',
    re.IGNORECASE,
)

# N+ years with N >= 3
N_PLUS_YEARS_PATTERN = re.compile(
    r'\b(\d+)\s*\+\s*(?:years?|yrs?)\b',
    re.IGNORECASE,
)

# Range X-Y years or X to Y years where min years >= 3
YEARS_RANGE_PATTERN = re.compile(
    r'\b(\d+)\s*(?:-|to)\s*(\d+)\s*(?:years?|yrs?)\b',
    re.IGNORECASE,
)

# At least / minimum / min N years where N >= 3
MIN_YEARS_PATTERN = re.compile(
    r'\b(?:at\s+least|minimum|min\.?)\s*(\d+)\s*(?:years?|yrs?)\b',
    re.IGNORECASE,
)

# N years of experience where N >= 3
EXPERIENCE_YEARS_PATTERN = re.compile(
    r'\b(\d+)\s*(?:years?|yrs?)\s*(?:of\s+)?experience\b',
    re.IGNORECASE,
)

# Explicit "no freshers"
NO_FRESHERS_PATTERN = re.compile(
    r'\b(?:no\s+freshers?|freshers?\s+(?:need\s+not\s+apply|do\s+not\s+apply|ineligible|cannot\s+apply)|not\s+open\s+to\s+freshers?)\b',
    re.IGNORECASE,
)

# Target batches allowed
TARGET_BATCHES = {2026, 2027, 2028}

# Batch restriction patterns like "batch 2024 only", "only 2024 graduates"
BATCH_RESTRICTION_PATTERNS = [
    re.compile(
        r'\b(?:batch(?:\s+of)?|graduat(?:ing|ion|es?)|passouts?)\s*[:\-]?\s*([0-9\s,\/andor]+)\s*(?:only|exclusively)\b',
        re.IGNORECASE,
    ),
    re.compile(
        r'\b(?:only|exclusive(?:ly)?\s+for)\s+(?:batch(?:\s+of)?|graduat(?:ing|ion|es?)|passouts?)\s*[:\-]?\s*([0-9\s,\/andor]+)\b',
        re.IGNORECASE,
    ),
    re.compile(
        r'\b(?:for\s+class\s+of|graduating\s+in)\s+([0-9\s,\/andor]+)\s+only\b',
        re.IGNORECASE,
    ),
]

# Explicit exclusion of target batches
TARGET_EXCLUSION_PATTERN = re.compile(
    r'\b(?:2026|2027|2028)\s+[^.\n]*(?:not\s+eligible|ineligible|need\s+not\s+apply|cannot\s+apply)\b',
    re.IGNORECASE,
)


def check_seniority_title(title: str) -> Optional[str]:
    match = SENIORITY_TITLE_PATTERN.search(title)
    if match:
        return f"Seniority word '{match.group(0)}' in title"
    return None


def check_level_title(title: str) -> Optional[str]:
    match = LEVEL_TITLE_PATTERN.search(title)
    if match:
        return f"Level marker '{match.group(0)}' in title (mid-level, not entry)"
    return None


def check_family_title(title: str) -> Optional[str]:
    if not FAMILY_TITLE_PATTERN.search(title):
        return "No role-family keyword in title (outside his verified skill families)"
    return None


def check_location_scope(location: Optional[str]) -> Optional[str]:
    if not location:
        return None
    if INDIA_LOCATION_PATTERN.search(location):
        return None
    if FOREIGN_LOCATION_PATTERN.search(location):
        return f"Location '{location}' is outside India scope with no India signal"
    return None


def check_experience_requirement(text: str) -> Optional[str]:
    # 1. Ranges first: an "X-Y years" range kills ONLY when its minimum is >= 3.
    range_matches = list(YEARS_RANGE_PATTERN.finditer(text))
    for m in range_matches:
        min_years = int(m.group(1))
        if min_years >= 3:
            return f"Experience range requirement {min_years}-{m.group(2)} years >= 3"

    # Mask the range spans so a sub-3 range's upper bound (e.g. the "3" in
    # "1-3 years of experience") cannot re-match below as a standalone demand.
    if range_matches:
        chars = list(text)
        for m in range_matches:
            for i in range(m.start(), m.end()):
                chars[i] = " "
        text = "".join(chars)

    # 2. Check "N+ years"
    for m in N_PLUS_YEARS_PATTERN.finditer(text):
        years = int(m.group(1))
        if years >= 3:
            return f"Experience requirement {years}+ years >= 3"

    # 3. Check "minimum N years"
    for m in MIN_YEARS_PATTERN.finditer(text):
        years = int(m.group(1))
        if years >= 3:
            return f"Minimum experience requirement {years} years >= 3"

    # 4. Check "N years [of] experience"
    for m in EXPERIENCE_YEARS_PATTERN.finditer(text):
        years = int(m.group(1))
        if years >= 3:
            return f"Experience requirement {years} years >= 3"

    return None


def check_freshers_exclusion(text: str) -> Optional[str]:
    # Explicit no freshers
    m = NO_FRESHERS_PATTERN.search(text)
    if m:
        return f"Explicit no-freshers exclusion: '{m.group(0)}'"

    # Explicit exclusion of target batches
    m = TARGET_EXCLUSION_PATTERN.search(text)
    if m:
        return f"Target batch excluded: '{m.group(0)}'"

    # Batch restriction only containing non-target years
    for pat in BATCH_RESTRICTION_PATTERNS:
        for match in pat.finditer(text):
            years = [int(y) for y in re.findall(r'\b(20\d\d)\b', match.group(1))]
            if years and not any(y in TARGET_BATCHES for y in years):
                return f"Graduation-year restriction to {years} excludes 2026/2027/2028"

    return None


def filter_posting(posting: Posting) -> FilterResult:
    """
    Deterministic fresher filter:
    - KILL only explicit exclusions:
      1) seniority words (senior, sr., staff, principal, lead, manager, director) in title
      2) experience demands >= 3 years in title or description, in the explicit forms
         enumerated in specs.md section 4 ("N+ years", ranges with minimum >= 3,
         "at least/minimum N years", "N years (of) experience")
      3) explicit "no freshers" / graduation-year exclusions other than 2026/2027/2028
    - PASS-THROUGH everything else (never kills on absence of a signal).
    """
    # 1. Seniority in title
    title_kill = check_seniority_title(posting.title)
    if title_kill:
        return FilterResult(passed=False, reason=title_kill)

    # 1b. Level markers in title (amendment 2026-10-23)
    level_kill = check_level_title(posting.title)
    if level_kill:
        return FilterResult(passed=False, reason=level_kill)

    # Combine text for content checks
    content = f"{posting.title}\n{posting.description_text or ''}"

    # 2. Experience requirement >= 3 years
    exp_kill = check_experience_requirement(content)
    if exp_kill:
        return FilterResult(passed=False, reason=exp_kill)

    # 3. Freshers / graduation year exclusions
    fresh_kill = check_freshers_exclusion(content)
    if fresh_kill:
        return FilterResult(passed=False, reason=fresh_kill)

    # 4. Role-family gate (amendment 2026-10-23)
    family_kill = check_family_title(posting.title)
    if family_kill:
        return FilterResult(passed=False, reason=family_kill)

    # 5. Location scope gate (amendment 2026-10-23)
    location_kill = check_location_scope(posting.location)
    if location_kill:
        return FilterResult(passed=False, reason=location_kill)

    # Otherwise pass through
    return FilterResult(passed=True, reason=None)
