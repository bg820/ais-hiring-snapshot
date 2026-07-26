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
    "intern", "internship", "fellowship", "resident", "residency",
    "junior", "jr.", "entry level", "entry-level", "new grad", "graduate",
    "trainee", "apprentice", "early career", "scholar",
]
SENIOR_MARKERS = [
    "senior", "sr.", "staff", "principal", "lead ", "lead,", "head of",
    "director", "vp ", "vice president", "chief", "founding", "manager",
    "expert", "distinguished",
]

# "Fellow" is two different jobs sharing one word, so it cannot be a plain
# marker. A *fellowship*, or a season-prefixed fellow ("Summer Fellow"), is a
# structured time-bound program and a real way in. A bare "Research Fellow" is
# a think-tank staff title that normally sits at or above an ordinary research
# hire: GovAI's own posting asks for "substantial research experience" and
# points less-experienced applicants at Research Scholar instead. So
# "fellowship" stays in ENTRY_MARKERS above, and bare "fellow" does not.
_PROGRAM_FELLOW = re.compile(
    r"\bfellows?\s+program\b"
    r"|\b(summer|winter|spring|fall|autumn|visiting|incoming)\s+fellows?\b", re.I)

# "Member of Technical Staff" is the standard *unleveled* individual-contributor
# title at AI labs, used for everyone from a first hire to a veteran. The "staff"
# marker is meant to catch the "Staff Engineer" rung, which is genuinely senior,
# so MTS titles are exempted rather than being read as seniority signals.
_MTS = re.compile(r"member of (the )?technical staff", re.I)


def seniority_from_title(title: str) -> str:
    t = f" {title.lower()} "
    if any(m in t for m in ENTRY_MARKERS) or _PROGRAM_FELLOW.search(t):
        return "entry"
    if _MTS.search(t):
        # Strip the exempted phrase, then look for any other seniority marker,
        # so "Senior Member of Technical Staff" still reads as senior.
        t = _MTS.sub(" ", t)
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
# Phrases that mark a "N years" mention as an experience floor. "Experience" is
# the common one, but plenty of postings state the same requirement as a track
# record or a background, e.g. Palisade's "proven track record of effectively
# advocating for policy changes for at least 5 years", which names no
# experience at all and was previously read as having no stated floor.
_EXP_CUES = ["experience", "track record", "background", "working in",
             "worked in", "spent"]


# A subordinate clause narrowing a requirement already stated, as in "5+ years
# of experience as an engineering manager, with at least 2 years leading growth
# teams". The 2 here is a slice of the 5, not a second, lower way in, and since
# the floor is taken as the smallest figure found, counting it would drag a
# senior role down into the entry-accessible bucket.
_SUBORDINATE = re.compile(
    r"(,\s*(with|including|of)\s+(a\s+minimum\s+of\s+|at\s+least\s+)?"
    r"|\bof which\s+)$", re.I)


TIGHT_BEFORE = 45  # what disqualifies a match must sit right next to it
CUE_AFTER = 60     # "15+ years of progressive accounting and controllership
                   # experience" puts the cue 46 characters past the number
CUE_BEFORE = 110   # the cue often opens the sentence ("a proven track record
                   # of ... for at least 5 years"), well before the number

# Some feeds hand back descriptions with HTML entities that survived escaping
# ("8+&nbsp; years of related contract management experience"). Left alone the
# entity sits between the number and the word "years" and the figure is missed
# altogether, so entities are flattened to plain spaces before matching.
_ENTITY = re.compile(r"&(?:nbsp|#160|#xa0|ensp|emsp|thinsp);|&amp;nbsp;", re.I)


def _year_spans(description):
    """Every plausible 'N years' figure as (start, end, years)."""
    spans = []
    for rgx, conv in ((_NUM_YEARS, lambda g: int(g)),
                      (_WORD_YEARS, lambda g: _WORD_NUM[g.lower()])):
        for m in rgx.finditer(description):
            y = conv(m.group(1))
            if 0 <= y <= 30:
                spans.append((m.start(), m.end(), y))
    return sorted(spans)


def _cue_spans(low):
    """Every experience-cue occurrence as (start, end)."""
    out = []
    for c in _EXP_CUES:
        i = low.find(c)
        while i != -1:
            out.append((i, i + len(c)))
            i = low.find(c, i + 1)
    return out


def _gap(span, cue):
    """Characters between a year figure and a cue; 0 if they overlap."""
    s, e = span[0], span[1]
    cs, ce = cue
    if cs < e and s < ce:
        return 0
    return cs - e if cs >= e else s - ce


def _eligible(low, span):
    """False for a figure that cannot be an experience floor at all.

    Disqualifying context ("in the past two years", "banned for two years")
    binds tightly to the number, so it is checked in a narrow window. A
    subordinate clause is not a second, lower way in.
    """
    s, e, _ = span
    tight_before = low[max(0, s - TIGHT_BEFORE):s]
    after = low[e:e + CUE_AFTER]
    if any(b in tight_before + " " + after for b in _BLACKLIST):
        return False
    return not _SUBORDINATE.search(tight_before)


def _owns_a_cue(span, eligible, cues):
    """Whether an experience cue sits near this figure and belongs to it.

    The cue that turns a figure into an experience floor often sits well before
    it ("a proven track record of ... for at least 5 years"), so it gets a long
    reach. But a long reach lets a figure borrow the cue from a neighbouring
    requirement, which is how "5-10 years of recruiting experience ... 2+ years
    recruiting for AI/ML" made a senior recruiting role look open to a
    beginner. So a cue counts only for whichever figure sits closest to it, and
    only figures still in the running compete for it.
    """
    s, e, _ = span
    for cue in cues:
        cs, ce = cue
        in_range = (s - CUE_BEFORE <= cs and ce <= s) or (e <= cs <= e + CUE_AFTER)
        if not in_range:
            continue
        mine = _gap(span, cue)
        if all(_gap(other, cue) >= mine for other in eligible if other != span):
            return True
    return False


def min_years_experience(description: str):
    """Smallest credibly-stated minimum years of experience, or None.

    Combines three signals (structured 'Required experience' field, numeric
    'N years' near an experience cue, and word-number 'two years'), and rejects
    non-experience uses of 'years' (visa residency, post-employment bans, etc.).
    """
    if not description:
        return None
    description = _ENTITY.sub(" ", description)
    low = description.lower()
    found = []

    for m in _REQ_ANCHOR.finditer(description):
        y = int(m.group(1))
        if 0 <= y <= 30:
            found.append(y)

    eligible = [sp for sp in _year_spans(description) if _eligible(low, sp)]
    cues = _cue_spans(low)
    for span in eligible:
        if _owns_a_cue(span, eligible, cues):
            found.append(span[2])

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
    """True if the role is plausibly within reach early in a career.

    An entry marker in the title settles it. Otherwise a stated floor of two
    years or less does, but only when the title carries no senior marker: an
    "Evals Infrastructure Tech Lead / Manager" asking for "1+ years managing
    engineers" is stating the smallest piece of a leadership job, not opening
    a door for a beginner, and the title is the more reliable signal.
    """
    seniority = seniority_from_title(title)
    if seniority == "entry":
        return True
    if seniority == "senior":
        return False
    y = min_years_experience(description)
    return y is not None and y <= 2
