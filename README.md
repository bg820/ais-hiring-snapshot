# AIS Hiring Snapshot

A reproducible look at hiring across AI-safety organizations, read straight from
each org's own hiring system. It answers one question: how steep is the
"entry-level cliff," meaning how few of the open roles are actually within reach
for someone early in their career?

Unlike the curated AIS job boards, this pulls directly from each org's hiring
feed (Greenhouse, Lever, Ashby), or from a small hand-kept supplement for the
orgs that have no machine-readable feed. So the dataset is the raw ground truth
rather than a hand-picked subset. Every org is listed in `orgs.csv` with its
source and whether it made the cut, so the coverage is easy to audit.

## What's here

- `orgs.csv`: the org registry (name, category, data source, identifier).
- `collectors/`: one collector per feed type (Greenhouse, Lever, Ashby).
- `manual_postings.csv`: hand-kept rows for orgs with no public feed.
- `classify.py`: the rule-based seniority and years-of-experience tagging.
- `collect.py`: pulls a dated snapshot into `data/snapshots/`.
- `build_site.py`: rebuilds the static site in `site/`.
- `data/snapshots/`: the committed CSV snapshots that make up the archive.

## Run it

```bash
pip install -r requirements.txt
python collect.py      # pull a dated snapshot into data/snapshots/
python build_site.py   # rebuild the static site into site/
```

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
  the roster in `orgs.csv` shows exactly which ones.
