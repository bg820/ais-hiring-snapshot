"""Checks on the classification rules, run with `python test_classify.py`.

Every case here is a real posting phrasing taken from the snapshots, kept so
that a future tweak to the rules cannot quietly undo a fix. Each one names the
posting it came from; the handful of guard cases with no real posting behind
them say "synthetic".
"""
import sys

from classify import (seniority_from_title, min_years_experience,
                      is_entry_accessible, is_expression_of_interest, function_of)

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
    # word boundaries (the 2026-09-30 fix)
    ("Director, US International Tax", "senior",
     "Anthropic: 'International' is not 'intern'"),
    ("Head of International Order-to-Cash", "senior", "Anthropic, same bug"),
    ("Internal Communications Manager, Tech", "unspecified",
     "Anthropic: 'Internal' is not 'intern' either"),
    ("Software Engineer Intern", "entry", "Haize Labs: a real intern still matches"),
    ("Leadership Coach", "unspecified", "synthetic: 'lead' must not match inside 'Leadership'"),
    # titles that name two rungs
    ("Researcher / Senior Researcher", "unspecified", "Epoch: open below senior"),
    ("Recruiter / Senior Recruiter", "unspecified", "Epoch, same"),
    ("(Senior) AI Governance Researcher", "unspecified", "Apollo, parenthesised"),
    ("Salesforce Architect or Senior Architect", "unspecified", "Coefficient Giving"),
    ("Software Engineer (all levels) - Core Technology", "entry",
     "UK AISI: explicitly open at every level, including the first"),
    # associate and manager
    ("Associate, Operations", "entry", "CAIS: the junior rung"),
    ("Hiring Associate", "entry", "GovAI"),
    ("Associate Director, Research", "senior", "synthetic: not the junior rung"),
    ("Product Manager, Website", "unspecified", "Epoch: function title, not a rung"),
    ("Office Manager (Part-Time)", "unspecified", "Apollo, same"),
    ("Senior Manager, People Operations", "senior", "CAIS: 'Senior' still counts"),
    ("Engineering Manager (Product)", "senior", "Apollo: a people-manager rung"),
    ("Staff+ Software Engineer, Backend and Infra", "senior", "Haize Labs"),
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
    ("You may be a good fit if you have 10+ years of experience in software "
     "engineering, solutions architecture, or a technical customer-facing role. "
     "2+ years of people management experience within a services organization", 10,
     "Anthropic: requirements stack, so the floor is the largest, not the smallest"),
    ("Have 8+ years of marketing experience with at least 2 years of experience in "
     "cybersecurity", 8, "Anthropic: a narrower slice of the main requirement"),
    ("Preferred qualifications 5+ years of experience in legal operations 2+ years "
     "of experience at a high-growth technology company", 5,
     "Anthropic: two stacked requirements"),
]

ENTRY = [
    ("Research Fellow", "Research Fellows are experienced researchers who conduct "
     "independent, high-quality research.", False,
     "the fix: GovAI's Research Fellow is not an early-career way in"),
    ("Research Engineer Intern", "", True, "title alone is enough"),
    ("Product Engineer", "You have 2+ years of experience building products.",
     True, "Goodfire: description floor of two years or less"),
    ("Research Scientist/Engineer (Evaluations)", "We don't require a formal "
     "background or industry experience and welcome self-taught candidates.", True,
     "Apollo: says so in the body, not the title"),
    ("Misuse Red Team - Research Engineer/Research Scientist", "We are open to "
     "hires at junior, senior, staff and principal research scientist levels.", True,
     "UK AISI"),
    ("Talent Program Manager", "For promising applicants who aren't yet in a "
     "position to take on the full range of responsibilities, we will consider "
     "making an offer at the Associate level first.", True, "GovAI"),
    ("Research Manager", "You can validate experiments and find the flaws in more "
     "junior researchers' work. Mentor and coach junior team members.", False,
     "CAIS/FAR: describing juniors you will manage is not an open door"),
    ("Head of Talent Operations", "Build the talent operations function that places "
     "early-career talent in high-impact AI safety roles.", False,
     "Kairos: early-career talent is who the job serves, not who can apply"),
    ("Litigation Counsel", "Explain litigation risk to non-legal audiences at all "
     "levels of seniority. Preferred qualifications: At least 12 years of experience.",
     False, "Anthropic: audiences at all levels are not applicants at all levels"),
    ("Enterprise Account Executive", "We hire across all levels of seniority. 7+ "
     "years of enterprise sales experience.", False,
     "synthetic: a stated floor above two years outranks a general welcome"),
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
    ("Join our Talent Community (future opportunities)", True, "LawZero"),
    ("The Role You Are Perfect For", True, "Irregular"),
    ("Shoot Your Shot", True, "standing application"),
    ("General Expression of Interest (EOI)", True, "Kairos"),
]

# (title, department, expected function, why)
FUNCTIONS = [
    ("Research Scientist (Control)", "", "Research", "Apollo"),
    ("Member of Technical Staff, Evaluation Execution", "", "Research", "METR"),
    ("AI Security Researcher", "", "Research", "Apollo: research on security"),
    ("Senior Security Engineer", "", "Security & IT", "Apollo"),
    ("Full-stack Software Engineer (Product)", "", "Engineering & product", "Apollo"),
    ("Research Manager (UK Fellowships)", "", "Programs & field-building", "GovAI"),
    ("Program Lead, Technical AI Safety Course", "", "Programs & field-building", "BlueDot"),
    ("Head of US Policy", "", "Policy & governance", "GovAI"),
    ("Account Executive, Life Sciences", "", "Go-to-market", "Goodfire"),
    ("Head of Deal Desk - International", "", "Go-to-market", "Anthropic"),
    ("Associate, Operations", "", "Operations", "CAIS"),
    ("Founding Recruiter", "", "Operations", "CAIS"),
    ("Chief of Staff", "", "Operations", "Goodfire"),
    ("Writer & Editor", "", "Comms & design", "Epoch"),
    ("Head of Communications & PR", "", "Comms & design", "Apollo"),
    ("Anthropic Fellows Program, AI Safety", "", "Programs & field-building", "Anthropic"),
    ("GTM Recruiter", "", "Operations", "Goodfire: recruiting, whatever the team"),
    ("Security Operations Lead", "", "Security & IT", "Goodfire"),
    ("System Administrator", "", "Security & IT", "METR"),
    ("Safeguards Enforcement Analyst, Bio Harms", "Safeguards (Trust & Safety)",
     "Security & IT", "Anthropic"),
    ("Something Unusual", "Finance", "Operations",
     "synthetic: falls back to the department"),
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

    for title, dept, want, why in FUNCTIONS:
        got = function_of(title, dept)
        if got != want:
            failures.append(f"function({title!r}) = {got!r}, want {want!r}  [{why}]")

    total = len(TITLES) + len(DESCRIPTIONS) + len(ENTRY) + len(EOI) + len(FUNCTIONS)
    if failures:
        print(f"FAILED {len(failures)} of {total} checks\n")
        for f in failures:
            print("  " + f)
        return 1
    print(f"All {total} classification checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
