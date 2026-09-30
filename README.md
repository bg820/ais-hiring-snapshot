# AIS Hiring Snapshot

A reproducible look at hiring across AI-safety organizations, read straight from
each org's own hiring system. It answers one question: what share of the jobs
these organizations are advertising could someone with two years of experience
or less realistically apply for?

The answer, from a hand-checked read of all 141 vacancies at 15 organizations on
2026-09-30: about 18% are open, 66% ask for more, and 16% don't say.

Unlike the curated AIS job boards, this pulls directly from each org's hiring
feed (Greenhouse, Lever, Ashby), so the dataset is the raw ground truth rather
than a hand-picked subset. Orgs without a readable feed are left out rather than
maintained by hand, and `orgs_excluded.csv` says who and why.

## What's here

- `orgs.csv`: the org registry (name, category, org type, data source, identifier).
  An org with two feeds (FAR.AI) has two rows.
- `orgs_excluded.csv`: orgs considered and left out, with the reason.
- `collectors/`: one collector per feed type (Greenhouse, Lever, Ashby).
- `classify.py`: the rules: title seniority, open-door statements, stated
  experience floor, and kind of work.
- `test_classify.py`: checks on those rules, each case a real posting phrasing.
- `audit/hand_labels_YYYY-MM-DD.csv`: every vacancy in one snapshot read by
  hand, with the line that decided each label. The findings page reports the
  newest audit; the rules keep the weekly figures current in between.
- `collect.py`: pulls a dated snapshot into `data/snapshots/`.
- `build_site.py`: rebuilds the static site in `site/`.
- `data/snapshots/`: the committed CSV snapshots that make up the archive.

## Run it

```bash
pip install -r requirements.txt
python collect.py        # pull a dated snapshot into data/snapshots/
python test_classify.py  # check the classification rules still hold
python build_site.py     # rebuild the static site into site/
```

After collecting, compare the per-org counts against the previous snapshot. A
hiring system that has been switched off returns an empty list rather than an
error, so an org that drops to zero usually means a moved feed, not a hiring
freeze. That is how the Center for AI Safety's move from Lever to Greenhouse
was caught on 2026-07-26.

## Upkeep

The weekly collection runs unattended. The only optional chore:

**Re-audit now and then (quarterly is plenty).** Copy the newest audit file to a
new date, label every concrete vacancy in the matching snapshot as `open`,
`closed` or `unclear` with a short evidence quote, and rebuild. `build_site.py`
refuses to build if any vacancy in the audited snapshot is unlabelled. The
method page reports how well the rules match the new labels, which is the real
test of rules written against the previous audit.

## Publish it

See [PUBLISHING.md](PUBLISHING.md) for a step-by-step guide to hosting the site
free on GitHub Pages and having it collect a fresh snapshot automatically every
week via GitHub Actions.

## Scope and limits

- Frontier labs (e.g. Anthropic) are tagged `frontier-lab` and kept out of the
  headline numbers, since most of their roles are not safety work. They show up
  only as a comparison.
- Job postings measure publicly advertised demand. Senior and network hiring
  often never gets posted, so this undercounts senior demand and should not be
  read as "where the field needs people most."
- Coverage is partial. Some orgs use systems with no machine-readable feed, and
  the roster in `orgs.csv` and `orgs_excluded.csv` shows exactly which ones.
- Fellowships (MATS, SPAR, GovAI's seasonal fellowships) are the main
  early-career route into the field and mostly recruit outside hiring systems,
  so they are largely missing here.
- Each snapshot CSV is about 6 MB, nearly all of it Anthropic's full job
  descriptions, so the repository grows by roughly that much each week.
