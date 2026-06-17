# AIS Hiring Snapshot

A reproducible, source-direct look at hiring across AI-safety organizations,
built to answer one precise question: **how steep is the "entry-level cliff" —
i.e., how few openings are actually accessible to people early in their careers?**

Unlike the curated AIS job boards, this pulls **directly from each org's own
hiring system** (their applicant-tracking feed, Airtable, or Notion), so the
dataset is the unfiltered ground truth rather than a hand-picked subset. Every
org considered is listed in `orgs.csv` with its source and inclusion status, so
coverage is fully auditable.

## What's here

- `orgs.csv` — the org registry: name, category, data source, identifier.
- `collectors/` — one collector per source type (Greenhouse, Lever, Ashby; Airtable/Notion in progress).
- `classify.py` — transparent, rule-based seniority + years-of-experience tagging.
- `collect.py` — pulls a dated snapshot into `data/snapshots/`.
- `data/snapshots/` — committed CSV snapshots (the reproducible dataset).

## Run it

```bash
pip install -r requirements.txt
python collect.py      # pull a dated snapshot into data/snapshots/
python build_site.py   # regenerate the static site into site/
```

## Publish it

See [PUBLISHING.md](PUBLISHING.md) for a step-by-step guide to hosting the site
free on GitHub Pages and having it **collect a fresh snapshot automatically every
week** via GitHub Actions.

## Scope & honesty notes

- **Frontier labs** (e.g. Anthropic) are tagged `frontier-lab` and kept **out of
  the headline metric** — most of their roles are not safety work. They appear
  only as an optional comparison.
- Job postings measure **publicly advertised** demand. Senior and network-based
  hiring often never gets posted, so this undercounts senior demand and should
  never be read as "where the field needs people most."
- Coverage is partial by construction (some orgs use systems with no machine-
  readable feed). The roster in `orgs.csv` makes the gaps explicit.
