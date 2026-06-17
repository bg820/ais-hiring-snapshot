"""Collectors for standard applicant-tracking systems with public JSON feeds.

Each function takes an org identifier (the ATS "slug") and returns a list of
normalized posting dicts. Normalized schema:

    org, source, ext_id, title, location, department, url, posted_at, description

`posted_at` is an ISO date string when available, else "".
Description text is captured when cheaply available (used later to parse
years-of-experience for the entry-level analysis); empty string otherwise.
"""
from __future__ import annotations
import requests

TIMEOUT = 12
UA = {"User-Agent": "ais-hiring-snapshot/0.1 (research; contact via repo)"}


def _get(url, **kw):
    return requests.get(url, headers=UA, timeout=TIMEOUT, **kw)


def greenhouse(slug: str) -> list[dict]:
    # content=true returns the HTML description and department info
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    r = _get(url)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        depts = j.get("departments") or []
        out.append({
            "ext_id": str(j.get("id", "")),
            "title": (j.get("title") or "").strip(),
            "location": ((j.get("location") or {}).get("name") or "").strip(),
            "department": depts[0]["name"] if depts and depts[0].get("name") else "",
            "url": j.get("absolute_url", ""),
            "posted_at": (j.get("first_published") or j.get("updated_at") or "")[:10],
            "description": _strip_html(j.get("content", "")),
        })
    return out


def lever(slug: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    r = _get(url)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    out = []
    for j in data:
        cats = j.get("categories") or {}
        created = j.get("createdAt")
        posted = ""
        if created:
            import datetime as _dt
            posted = _dt.datetime.utcfromtimestamp(created / 1000).date().isoformat()
        out.append({
            "ext_id": str(j.get("id", "")),
            "title": (j.get("text") or "").strip(),
            "location": (cats.get("location") or "").strip(),
            "department": (cats.get("team") or cats.get("department") or "").strip(),
            "url": j.get("hostedUrl", ""),
            "posted_at": posted,
            "description": (j.get("descriptionPlain") or "").strip(),
        })
    return out


def ashby(slug: str) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    r = _get(url)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "ext_id": str(j.get("id", "")),
            "title": (j.get("title") or "").strip(),
            "location": (j.get("location") or "").strip(),
            "department": (j.get("department") or j.get("team") or "").strip(),
            "url": j.get("jobUrl") or j.get("applyUrl") or "",
            "posted_at": (j.get("publishedAt") or "")[:10],
            "description": (j.get("descriptionPlain") or "").strip(),
        })
    return out


def _strip_html(s: str) -> str:
    import html
    import re
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


COLLECTORS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
