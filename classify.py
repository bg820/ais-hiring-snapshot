"""Transparent, rule-based classification for the entry-level analysis.

Two independent signals, both published so anyone can audit them:

1. seniority_from_title(): explicit seniority markers in the job title.
   Buckets: entry, senior, unspecified. We deliberately do NOT guess a
   "mid" level from an unmarked title, an unmarked "Research Engineer"
   tells us nothing reliable about the experience floor, so it stays
   "unspecified" rather than inflating either end.

2. min_years_experience(): the smallest "N+ years" figure mentioned in the
   description, as a proxy for the experience floor. Returns None when the
   text states no explicit requirement.

The headline "entry-level cliff" metric combines these: a role counts as
entry-accessible if the title carries an entry marker OR the description's
minimum stated experience is <= 2 years.
"""
from __future__ import annotations
import re

ENTRY_MARKERS = [
    "intern", "internship", "fellow", "fellowship", "resident", "residency",
    "junior", "jr.", "entry level", "entry-level", "new grad", "graduate",
    "trainee", "apprentice", "early career", "scholar",
]
SENIOR_MARKERS = [
    "senior", "sr.", "staff", "principal", "lead ", "lead,", "head of",
    "director", "vp ", "vice president", "chief", "founding", "manager",
    "expert", "distinguished",
]


def seniority_from_title(title: str) -> str:
    t = f" {title.lower()} "
    if any(m in t for m in ENTRY_MARKERS):
        return "entry"
    if any(m in t for m in SENIOR_MARKERS):
        return "senior"
    return "unspecified"


_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}

# A "N years" / "N+ years" / "N-M years" / "two years" mention.
_NUM_YEARS = re.compile(
    r"(?<![\w.])(\d{1,2})\s*\+?\s*(?:(?:to|-|-|)\s*\d{1,2}\s*\+?)?\s*years?\b", re.I)
_WORD_YEARS = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+years?\b", re.I)

# "Required experience: 5+ years ...", the structured-field pattern several
# ATS templates use; the number right after is the experience floor.
_REQ_ANCHOR = re.compile(r"required experience\D{0,25}(\d{1,2})\s*\+?", re.I)

# Contexts where "N years" is NOT an experience requirement.
_BLACKLIST = ["banned", "resident", "residenc", "the past", "past ", "next ",
              "ago", "civil service", "further employment", "from further",
              "undergo", "over the last", "last ", "every ", "for the past",
              "within the next", "per year", "a year", "years old"]
def _accept(low_before, low_after, raw_after):
    """A 'N years' mention counts only if an experience cue sits right next to
    it and no non-experience context (residency, bans, etc.) does."""
    win = low_before + " " + low_after
    if any(b in win for b in _BLACKLIST):
        return False
    return "experience" in low_before or "experience" in low_after[:30]


def min_years_experience(description: str):
    """Smallest credibly-stated minimum years of experience, or None.

    Combines three signals (structured 'Required experience' field, numeric
    'N years' near an experience cue, and word-number 'two years'), and rejects
    non-experience uses of 'years' (visa residency, post-employment bans, etc.).
    """
    if not description:
        return None
    low = description.lower()
    found = []

    for m in _REQ_ANCHOR.finditer(description):
        y = int(m.group(1))
        if 0 <= y <= 30:
            found.append(y)

    def scan(rgx, to_int):
        for m in rgx.finditer(description):
            y = to_int(m.group(1))
            if not (0 <= y <= 30):
                continue
            s, e = m.start(), m.end()
            if _accept(low[max(0, s - 45):s], low[e:e + 45], description[e:e + 40]):
                found.append(y)

    scan(_NUM_YEARS, lambda g: int(g))
    scan(_WORD_YEARS, lambda g: _WORD_NUM[g.lower()])

    return min(found) if found else None


_EOI_MARKERS = ["expression of interest", "expressions of interest",
                "general interest", "exceptional talent", "talent pool",
                "talent network", "general application"]


def is_expression_of_interest(title: str) -> bool:
    """True for standing talent-pool / 'register your interest' listings, which
    are invitations to apply rather than posted vacancies. Excluded from the
    concrete-openings metrics, reported separately."""
    t = (title or "").lower()
    return any(m in t for m in _EOI_MARKERS)


def is_entry_accessible(title: str, description: str) -> bool:
    if seniority_from_title(title) == "entry":
        return True
    y = min_years_experience(description)
    return y is not None and y <= 2
