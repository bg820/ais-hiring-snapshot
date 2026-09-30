"""Transparent, rule-based classification for the entry-level analysis.

Three independent signals, all published so anyone can audit them:

1. seniority_from_title(): explicit seniority markers in the job title.
   Buckets: entry, senior, unspecified. We deliberately do NOT guess a
   "mid" level from an unmarked title, an unmarked "Research Engineer"
   tells us nothing reliable about the experience floor, so it stays
   "unspecified" rather than inflating either end.

2. min_years_experience(): the experience floor a posting states, taken as
   the LARGEST credible "N+ years" requirement in the description. Returns
   None when the text states no explicit requirement. (Until 2026-09-30 this
   took the smallest figure, which read "10+ years in engineering ... 2+ years
   of people management" as a two-year floor. Listed requirements are
   normally all required at once, so the binding one is the largest.)

3. function_of(): what kind of work the role is (research, engineering,
   operations, ...), from the title with the ATS department as a fallback.

The headline "entry-level cliff" metric combines the first two: a role counts
as entry-accessible if the title carries an entry marker OR the description's
minimum stated experience is <= 2 years (and the title carries no senior
marker).

Every marker is matched on word boundaries. Plain substring matching read
"International" as "intern", which put "Director, US International Tax" in
the early-career bucket; that bug inflated the frontier-lab comparison until
2026-09-30.
"""
from __future__ import annotations
import re


def _words(*phrases):
    """One regex matching any of the phrases as whole words."""
    alts = "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in phrases)
    return re.compile(rf"(?<![a-z])(?:{alts})(?![a-z])", re.I)


ENTRY_MARKERS = [
    "intern", "interns", "internship", "fellowship", "resident", "residency",
    "junior", "jr", "entry level", "entry-level", "new grad", "graduate",
    "trainee", "apprentice", "early career", "early-career", "scholar",
    "all levels", "any level", "all experience levels",
]
SENIOR_MARKERS = [
    "senior", "sr", "staff", "staff+", "principal", "lead", "head of",
    "director", "vp", "vice president", "chief", "founding",
    "engineering manager", "expert", "distinguished", "partner",
]
_ENTRY = _words(*ENTRY_MARKERS)
_SENIOR = _words(*SENIOR_MARKERS)

# "Associate" is the junior rung at nonprofits and think tanks ("Associate,
# Operations", "Hiring Associate", "Research Management Associate"), but it is
# the opposite in "Associate Director" or "Associate Professor".
_ASSOCIATE = re.compile(
    r"(?<![a-z])associate(?![a-z])(?!\s+(director|professor|partner|principal"
    r"|general counsel|vice president|dean))", re.I)

# "Fellow" is two different jobs sharing one word, so it cannot be a plain
# marker. A *fellowship*, or a season-prefixed fellow ("Summer Fellow"), is a
# structured time-bound program and a real way in. A bare "Research Fellow" is
# a think-tank staff title that normally sits at or above an ordinary research
# hire: GovAI's own posting describes its Research Fellows as "experienced
# researchers" who "mentor early-career researchers". So "fellowship" stays in
# ENTRY_MARKERS above, and bare "fellow" does not.
_PROGRAM_FELLOW = re.compile(
    r"\bfellows?\s+program\b"
    r"|\b(summer|winter|spring|fall|autumn|visiting|incoming)\s+fellows?\b", re.I)

# "Member of Technical Staff" is the standard *unleveled* individual-contributor
# title at AI labs, used for everyone from a first hire to a veteran. The "staff"
# marker is meant to catch the "Staff Engineer" rung, which is genuinely senior,
# so MTS titles are exempted rather than being read as seniority signals.
# "Chief of Staff" is exempted from nothing: "chief" catches it on its own.
_MTS = re.compile(r"member of (the )?technical staff", re.I)

# A title that names two rungs, "Researcher / Senior Researcher", "Recruiter /
# Senior Recruiter", "(Senior) AI Governance Researcher", "Architect or Senior
# Architect", is explicitly open below senior. Reading the word "senior" in it
# as a senior-only role was a bug. Such titles are left unspecified: they are
# not senior-only, but they do not promise an early-career way in either.
_RANGE = re.compile(
    r"\(senior\)|\bsenior\s*/|/\s*senior\b|\bor\s+senior\b|\bsenior\s+or\b", re.I)

# Bare "Manager" is left out of the senior list on purpose. In a function title
# ("Product Manager", "Office Manager", "Social Media & Community Manager",
# "Research Manager") it names the job, not the rung, and several of these are
# posted with an associate-level alternative. Manager titles that do name a
# rung, "Senior Manager", "Engineering Manager", "Head of ...", still count.


def seniority_from_title(title: str) -> str:
    t = f" {(title or '').lower()} "
    if _ENTRY.search(t) or _PROGRAM_FELLOW.search(t) or _ASSOCIATE.search(t):
        return "entry"
    if _RANGE.search(t):
        return "unspecified"
    if _MTS.search(t):
        # Strip the exempted phrase, then look for any other seniority marker,
        # so "Senior Member of Technical Staff" still reads as senior.
        t = _MTS.sub(" ", t)
    if _SENIOR.search(t):
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
    """The stated experience floor in years (largest credible figure), or None.

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

    return max(found) if found else None


_EOI_MARKERS = ["expression of interest", "expressions of interest",
                "general interest", "exceptional talent", "talent pool",
                "talent network", "talent community", "general application",
                "open application", "future opportunities", "shoot your shot",
                "the role you are perfect for", "don't see", "(eoi)"]


def is_expression_of_interest(title: str) -> bool:
    """True for standing talent-pool / 'register your interest' listings, which
    are invitations to apply rather than posted vacancies. Excluded from the
    concrete-openings metrics, reported separately."""
    t = (title or "").lower()
    return any(m in t for m in _EOI_MARKERS)


# Plain statements, in the body of a posting, that the role is open below the
# senior level: "We are open to hires at junior, senior, staff and principal
# levels", "We don't require a formal background or industry experience and
# welcome self-taught candidates", "we will consider making an offer at the
# Associate level first". The 2026-09-30 hand audit found that most postings
# open to early-career applicants say so here rather than in the title.
#
# These phrases were written after reading that snapshot, so the rules agree
# with it partly by construction. The honest test is how they do on postings
# they were not written from.
#
# The phrases are narrow on purpose. "Mentor junior team members", "support
# early-career researchers", "places early-career talent" and "communicate
# with audiences at all levels of seniority" describe the job, not who can
# apply, and must not match.
_OPEN_DOOR = re.compile("|".join([
    r"open to (hires|candidates|applicants) (at|across|of|from) (all|junior|a range|a variety|any)",
    r"\b(at|across) all (experience|seniority) levels",
    r"\b(hire|hires|hiring|candidates|applicants|people)\s+(at|across|of|from)\s+all\s+levels",
    r"\bfrom junior (through|to)\b",
    r"\bjunior, (mid|senior)",
    r"\bopen on seniority\b",
    r"range of (levels of experience|experience levels|seniority)",
    r"variety of (seniority|experience) levels",
    r"(don.t|do not) require (a )?formal background",
    r"welcome self-taught",
    r"without (industrial|industry) experience",
    r"\bnew to (ml|machine learning)\b",
    r"offer at the associate level",
    r"associate (position|role|level) first",
    r"\bearly[- ]career roles?\b",
    r"no (prior |previous )?experience (is )?(required|necessary|needed)",
    r"\brecent graduates?\b",
]), re.I)


def says_open_below_senior(description: str) -> bool:
    """True if the posting's text plainly invites below-senior applicants."""
    return bool(description) and bool(_OPEN_DOOR.search(_ENTITY.sub(" ", description)))


def is_entry_accessible(title: str, description: str) -> bool:
    """True if the role is plausibly within reach early in a career.

    An entry marker in the title settles it. Otherwise a stated floor of two
    years or less does, or a plain statement in the text that junior or
    self-taught applicants are welcome (unless the text also states a floor
    above two years), but only when the title carries no
    senior marker: an "Evals Infrastructure Tech Lead / Manager" asking for
    "1+ years managing engineers" is stating the smallest piece of a
    leadership job, not opening a door for a beginner, and the title is the
    more reliable signal.
    """
    seniority = seniority_from_title(title)
    if seniority == "entry":
        return True
    if seniority == "senior":
        return False
    y = min_years_experience(description)
    if y is not None and y > 2:
        # A stated floor above two years outranks a general welcome.
        return False
    return says_open_below_senior(description) or y is not None


# ---------- function ----------
# Ordered: the first bucket whose pattern matches the title wins, so the more
# specific buckets come first ("Research Manager" is programme work, not
# research; "Product Security Engineer" is security, not product). The ATS
# department is consulted only when the title matches nothing.
FUNCTIONS = [
    ("Programs & field-building", _words(
        "program lead", "program manager", "programme manager", "programs", "fellowship",
        "research manager", "research management", "talent program", "workshops",
        "groups", "special projects", "fellows program", "talent operations",
        "talent ops", "field-building", "course")),
    ("Policy & governance", _words(
        "policy", "governance", "regulatory", "national security", "congressional",
        "government affairs", "public affairs", "legislative")),
    ("Go-to-market", _words(
        "account executive", "sales", "sdr", "business development", "deal desk",
        "demand generation", "marketing", "growth", "partnerships", "customer",
        "solutions architect", "engagement manager", "vertical lead", "vertical ai lead",
        "go-to-market", "gtm", "revenue", "pre-sales", "slinger", "order-to-cash",
        "salesforce", "applied ai")),
    ("Operations", _words(
        "operations", "ops", "finance", "financial", "accountant", "accounting",
        "tax", "people", "recruiter", "recruiting", "hiring", "talent", "chief of staff",
        "executive assistant", "office", "counsel", "legal", "compliance", "payroll",
        "hr", "workplace", "events", "event", "admin", "procurement",
        "controller", "treasury", "facilities", "entrepreneur-in-residence",
        "project manager")),
    ("Comms & design", _words(
        "communications", "comms", "writer", "editor", "video", "design", "designer",
        "social media", "community", "brand", "content", "producer", "pr",
        "journalist", "illustrator")),
    ("Security & IT", _words(
        "security", "it", "cyber", "system administrator", "sysadmin", "ciso",
        "devops", "sre", "site reliability", "safeguards", "threat intel",
        "trust & safety")),
    ("Research", _words(
        "research", "researcher", "scientist", "member of technical staff",
        "evals", "evaluation", "evaluations", "red team", "interpretability",
        "alignment", "task development", "benchmark", "forensics", "mathematical")),
    ("Engineering & product", _words(
        "engineer", "engineering", "developer", "software", "platform",
        "infrastructure", "data", "machine learning", "ml", "product", "compute",
        "technical", "technician", "architect", "full-stack", "backend", "frontend")),
]

# Titles that match two buckets are settled by the most specific cue: a
# "Cyber Researcher" or "AI Security Researcher" is research on security, and
# a "Security Engineer" is security work. These cues pull a title into
# Research before the Security & IT check runs.
_RESEARCH_FIRST = _words("researcher", "research scientist", "research engineer",
                         "red team", "research lead")
# Likewise a "GTM Recruiter" recruits (Operations) and a "Security Operations
# Lead" or "System Administrator" runs security and IT.
_OPS_FIRST = _words("recruiter", "recruiting", "counsel")
_SECURITY_FIRST = _words("security operations", "system administrator")


def function_of(title: str, department: str = "") -> str:
    t = title or ""
    if _SECURITY_FIRST.search(t):
        return "Security & IT"
    if _OPS_FIRST.search(t):
        return "Operations"
    if _RESEARCH_FIRST.search(t) and not FUNCTIONS[0][1].search(t) \
            and not FUNCTIONS[1][1].search(t):
        return "Research"
    for name, rgx in FUNCTIONS:
        if rgx.search(t):
            return name
    for name, rgx in FUNCTIONS:
        if department and rgx.search(department):
            return name
    return "Other"
