"""Checks on the classification rules, run with `python test_classify.py`.

Every case here is a real posting phrasing taken from the snapshots, kept so
that a future tweak to the rules cannot quietly undo a fix. Each one names the
posting it came from.
"""
import sys

from classify import (seniority_from_title, min_years_experience,
                      is_entry_accessible, is_expression_of_interest)

# (title, expected bucket, why)
TITLES = [
    ("Research Engineer Intern", "entry", "plain internship"),
    ("DC Winter Fellowship 2027", "entry", "structured fellowship program"),
    ("Anthropic Fellows Program, AI Safety", "entry", "fellows program"),
    ("Summer Fellow", "entry", "season-prefixed program fellow"),
    ("Research Scholar", "entry", "GovAI's career-development visiting role"),
    ("Research Fellow", "unspecified",
     "GovAI: think-tank staff title wanting substantial experience, not a program"),
    ("Senior Research Fellow", "senior", "explicit senior marker still wins"),
    ("Member of Technical Staff", "unspecified",
     "METR/Redwood: unleveled IC title, not the 'Staff Engineer' rung"),
    ("Field Team - Member of Technical Staff", "unspecified", "Goodfire, same"),
    ("Senior Member of Technical Staff", "senior", "exemption must not swallow 'senior'"),
    ("Staff Software Engineer", "senior", "the real Staff rung"),
    ("Chief of Staff", "senior", "CAIS"),
    ("Head of US Policy", "senior", "GovAI"),
    ("Congressional Policy Lead", "senior", "Palisade"),
    ("Research Scientist", "unspecified", "no marker either way"),
]

# (description, expected minimum years, why)
DESCRIPTIONS = [
    ("proven track record of effectively advocating for policy changes for at "
     "least 5 years across a range of stakeholders", 5,
     "Palisade: floor stated as a track record, with no word 'experience'"),
    ("Required experience 5-10 years of recruiting experience, with 3+ years in "
     "early-stage startups 2+ years recruiting specifically for AI/ML", 5,
     "Goodfire: later bullets must not borrow the first bullet's cue"),
    ("You may be a good fit if you have: 7+ years of experience as a Solutions "
     "Architect, or similar pre-sales role 2+ years leading pre-sales practitioners", 7,
     "Anthropic: same, across a bullet boundary"),
    ("5+ years of experience as an engineering manager, with at least 2 years "
     "leading growth teams", 5,
     "a subordinate clause narrows the requirement, it is not a lower way in"),
    ("Preferred Qualifications: 7+ years of related contract management "
     "experience, with at least 3 years of experience supporting transactions", 7,
     "Anthropic: the headline figure still counts when the sub-clause is dropped"),
    ("Have an engineering background and 2+ years in product management", 2,
     "'background' is an experience cue too"),
    ("You may be a good fit if you have: 8+ years of enterprise sales experience "
     "in Japan", 8,
     "the cue sits just past the old 30-character cutoff"),
    ("You must not have been banned from the civil service in the past two years",
     None, "UK AISI: a post-employment ban, not experience"),
    ("Contracts are full-time and last two years on a fixed-term basis", None,
     "GovAI: contract length, not experience"),
    ("This is a two-year fixed term contract", None, "hyphenated, not a floor"),
    ("", None, "no description"),
]

ENTRY = [
    ("Research Fellow", "Successful applicants will have substantial research "
     "experience in a relevant area.", False,
     "the fix: GovAI's Research Fellow is not an early-career way in"),
    ("Research Engineer Intern", "", True, "title alone is enough"),
    ("Product Engineer", "You have 2+ years of experience building products.",
     True, "Goodfire: description floor of two years or less"),
    ("Senior Technical Recruiter",
     "Required experience 5-10 years of recruiting experience, with 3+ years in "
     "early-stage startups 2+ years recruiting specifically for AI/ML", False,
     "must not read as entry-accessible"),
]

EOI = [
    ("Expression of Interest", True, "CAIS"),
    ("Exceptional Talent", True, "Apart / BlueDot standing application"),
    ("General Expression of Interest", True, "METR"),
    ("Director of Operations - Expressions of Interest", True, "GovAI, plural"),
    ("Research Scientist", False, "an ordinary vacancy"),
]


def main():
    failures = []

    for title, want, why in TITLES:
        got = seniority_from_title(title)
        if got != want:
            failures.append(f"seniority({title!r}) = {got!r}, want {want!r}  [{why}]")

    for desc, want, why in DESCRIPTIONS:
        got = min_years_experience(desc)
        if got != want:
            failures.append(f"min_years({desc[:55]!r}...) = {got!r}, want {want!r}  [{why}]")

    for title, desc, want, why in ENTRY:
        got = is_entry_accessible(title, desc)
        if got != want:
            failures.append(f"entry_accessible({title!r}) = {got!r}, want {want!r}  [{why}]")

    for title, want, why in EOI:
        got = is_expression_of_interest(title)
        if got != want:
            failures.append(f"is_eoi({title!r}) = {got!r}, want {want!r}  [{why}]")

    total = len(TITLES) + len(DESCRIPTIONS) + len(ENTRY) + len(EOI)
    if failures:
        print(f"FAILED {len(failures)} of {total} checks\n")
        for f in failures:
            print("  " + f)
        return 1
    print(f"All {total} classification checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
