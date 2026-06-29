"""Pull a dated snapshot of postings across the org registry (orgs.csv).

Usage:  python collect.py

Writes data/snapshots/snapshot_YYYY-MM-DD.csv and prints a per-org summary.
Sources that are not yet wired up (identifier == PENDING) are skipped and
reported, so the coverage roster stays plain.
"""
from __future__ import annotations
import csv
import datetime as dt
import os
import sys

from collectors import ats

HERE = os.path.dirname(os.path.abspath(__file__))
ORGS = os.path.join(HERE, "orgs.csv")
MANUAL = os.path.join(HERE, "manual_postings.csv")
SNAP_DIR = os.path.join(HERE, "data", "snapshots")

FIELDS = ["org", "category", "source", "collection_method", "ext_id", "title",
          "location", "department", "url", "posted_at", "captured_at", "description"]


def load_orgs():
    with open(ORGS, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def collect_one(org):
    src = org["source"].strip()
    ident = org["identifier"].strip()
    if ident == "manual":
        return None, "via manual supplement"
    if ident == "PENDING" or src not in ats.COLLECTORS:
        return None, f"pending ({src}, needs browser capture)"
    try:
        rows = ats.COLLECTORS[src](ident)
        return rows, f"{len(rows)} roles"
    except Exception as e:
        return None, f"ERROR: {type(e).__name__}: {e}"


def main():
    orgs = load_orgs()
    today = dt.date.today().isoformat()
    captured = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    os.makedirs(SNAP_DIR, exist_ok=True)
    out_path = os.path.join(SNAP_DIR, f"snapshot_{today}.csv")

    all_rows = []
    print(f"Collecting snapshot for {today}\n" + "-" * 52)
    for org in orgs:
        rows, status = collect_one(org)
        print(f"  {org['name']:28s} {status}")
        if not rows:
            continue
        for r in rows:
            r.update(org=org["name"], category=org["category"], source=org["source"],
                     collection_method="api", captured_at=captured)
            all_rows.append({k: r.get(k, "") for k in FIELDS})

    # Merge the hand-maintained supplement for orgs with no machine-readable feed.
    n_manual = 0
    if os.path.exists(MANUAL):
        with open(MANUAL, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not r.get("title", "").strip():
                    continue
                r.setdefault("source", "manual")
                r["collection_method"] = "manual"
                r.setdefault("captured_at", captured)
                all_rows.append({k: r.get(k, "") for k in FIELDS})
                n_manual += 1
    print(f"  {'(manual supplement)':28s} {n_manual} roles")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_rows)

    print("-" * 52)
    print(f"Total roles: {len(all_rows)}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    sys.exit(main())
