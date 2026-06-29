"""Build the static site from the latest snapshot.

    python build_site.py

Reads the newest data/snapshots/*.csv, classifies roles, builds the charts,
and writes a self-contained static site into site/ (index, methodology,
coverage). Publishable as-is to GitHub Pages. Re-run to regenerate everything.
"""
from __future__ import annotations
import csv
import glob
import os
import datetime as dt
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from classify import seniority_from_title, min_years_experience, is_entry_accessible

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
# Auto-fills from the GitHub Actions environment; falls back to a placeholder
# you can hard-code if you ever build outside CI.
_gh_repo = os.environ.get("GITHUB_REPOSITORY")
REPO_URL = f"https://github.com/{_gh_repo}" if _gh_repo else "https://github.com/USERNAME/ais-hiring-snapshot"

INK = "#1a2233"; MUTE = "#5b6472"; ACCENT = "#c1452e"; SENIOR = "#9aa3b0"
ENTRY = "#2e7d57"; UNSPEC = "#d8a13a"; GRID = "#e7e9ee"
pio.templates.default = "plotly_white"


def latest_snapshot():
    files = sorted(glob.glob(os.path.join(HERE, "data", "snapshots", "*.csv")))
    if not files:
        raise SystemExit("No snapshot found — run collect.py first.")
    return files[-1]


def load():
    path = latest_snapshot()
    df = pd.read_csv(path).fillna("")
    df["seniority"] = df.title.map(seniority_from_title)
    df["min_years"] = df.description.map(min_years_experience)
    df["entry_ok"] = df.apply(lambda r: is_entry_accessible(r.title, r.description), axis=1)
    snap_date = os.path.basename(path).replace("snapshot_", "").replace(".csv", "")
    return df, snap_date


_JS_EMBEDDED = [False]  # embed the plotly library inline exactly once per page set


def fig_html(fig, height=360):
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=height,
                      font=dict(color=INK, size=14), legend=dict(orientation="h", y=-0.18),
                      paper_bgcolor="white", plot_bgcolor="white")
    fig.update_xaxes(gridcolor=GRID); fig.update_yaxes(gridcolor=GRID)
    if not _JS_EMBEDDED[0]:
        include = True  # inline the full library on the first chart -> always renders
        _JS_EMBEDDED[0] = True
    else:
        include = False
    return fig.to_html(full_html=False, include_plotlyjs=include,
                       config={"displayModeBar": False})


def chart_seniority(native):
    order = ["entry", "unspecified", "senior"]
    labels = {"entry": "Entry-marked", "unspecified": "Unspecified", "senior": "Senior-marked"}
    counts = native.seniority.value_counts()
    vals = [int(counts.get(k, 0)) for k in order]
    colors = [ENTRY, UNSPEC, SENIOR]
    fig = go.Figure(go.Bar(x=[labels[k] for k in order], y=vals,
                           marker_color=colors, text=vals, textposition="outside"))
    fig.update_layout(yaxis_title="Open roles", title="Seniority signal in job titles")
    return fig_html(fig)


def chart_by_org(native):
    piv = (native.groupby(["org", "seniority"]).size().unstack(fill_value=0)
           .reindex(columns=["entry", "unspecified", "senior"], fill_value=0))
    piv = piv.loc[piv.sum(axis=1).sort_values().index]
    fig = go.Figure()
    for k, c, name in [("senior", SENIOR, "Senior-marked"),
                       ("unspecified", UNSPEC, "Unspecified"),
                       ("entry", ENTRY, "Entry-marked")]:
        fig.add_bar(y=piv.index, x=piv[k], name=name, orientation="h", marker_color=c)
    fig.update_layout(barmode="stack", title="Roles by org and seniority",
                      xaxis_title="Open roles")
    return fig_html(fig, height=380)


def chart_minyears(native):
    got = native[native.min_years.notna()]
    vc = got.min_years.astype(int).value_counts().sort_index()
    fig = go.Figure(go.Bar(x=[f"{y}y" for y in vc.index], y=vc.values,
                           marker_color=ACCENT, text=vc.values, textposition="outside"))
    fig.update_layout(yaxis_title="Roles", xaxis_title="Minimum years required",
                      title=f"Stated experience floor (where given, n={len(got)})")
    return fig_html(fig, height=300)


def chart_compare(native, labs):
    groups = [("AIS-native orgs", native), ("Anthropic (frontier lab)", labs)]
    names = [g[0] for g in groups]
    shares = [round(g[1].entry_ok.mean() * 100, 1) if len(g[1]) else 0 for g in groups]
    fig = go.Figure(go.Bar(x=names, y=shares, marker_color=[ACCENT, SENIOR],
                           text=[f"{s}%" for s in shares], textposition="outside"))
    fig.update_layout(yaxis_title="% of open roles", yaxis_range=[0, max(shares + [10]) * 1.3],
                      title="Share of roles accessible early-career")
    return fig_html(fig, height=320)


# ---------- HTML template ----------
CSS = """
:root{--ink:#1a2233;--mute:#5b6472;--accent:#c1452e;--line:#e7e9ee;--bg:#fbfbfc}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",
Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.62}
.wrap{max-width:820px;margin:0 auto;padding:0 22px}
header.site{border-bottom:1px solid var(--line);background:#fff}
header.site .wrap{display:flex;justify-content:space-between;align-items:center;padding:16px 22px}
header.site a.brand{font-weight:700;text-decoration:none;color:var(--ink);font-size:15px}
nav a{color:var(--mute);text-decoration:none;margin-left:18px;font-size:14px}
nav a:hover{color:var(--accent)}
h1{font-size:34px;line-height:1.2;margin:34px 0 6px}
h2{font-size:22px;margin:38px 0 10px}
.lede{font-size:18px;color:var(--mute);margin:0 0 8px}
.meta{font-size:13px;color:var(--mute);margin:6px 0 26px}
.stat{display:flex;gap:26px;flex-wrap:wrap;margin:26px 0}
.stat .n{font-size:40px;font-weight:700;color:var(--accent);line-height:1}
.stat .l{font-size:13px;color:var(--mute);max-width:170px;margin-top:6px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px;margin:18px 0}
.callout{background:#fff7f4;border:1px solid #f0d2c8;border-radius:10px;padding:14px 16px;font-size:14px;color:#7a3a2c}
table{border-collapse:collapse;width:100%;font-size:14px;margin:12px 0}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mute);font-weight:600}
.tag{display:inline-block;font-size:11px;padding:2px 7px;border-radius:20px}
.tag.api{background:#e6f3ec;color:#2e7d57}.tag.manual{background:#fdf0d8;color:#9a6b13}
.tag.out{background:#eceef2;color:#5b6472}
footer{border-top:1px solid var(--line);margin-top:50px;padding:24px 0;color:var(--mute);font-size:13px}
code{background:#eef0f4;padding:1px 5px;border-radius:4px;font-size:13px}
small{color:var(--mute)}
"""

PLOTLY_CDN = ''  # the plotly library is embedded inline by fig_html (first chart)


def page(title, body, active):
    nav = ""
    for href, label in [("index.html", "Findings"), ("methodology.html", "Method"),
                        ("coverage.html", "Coverage")]:
        nav += f'<a href="{href}"{" style=color:var(--accent)" if href==active else ""}>{label}</a>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}</style>{PLOTLY_CDN}</head>
<body><header class="site"><div class="wrap"><a class="brand" href="index.html">AIS Hiring Snapshot</a>
<nav>{nav}</nav></div></header><main class="wrap">{body}</main>
<footer><div>Source-direct dataset · reproducible · <a href="{REPO_URL}">code &amp; data</a>.
Built {dt.date.today().isoformat()}. Job postings measure publicly advertised demand only.</div></footer>
</body></html>"""


def build():
    df, snap = load()
    native = df[df.category != "frontier-lab"].copy()
    labs = df[df.org == "Anthropic"].copy()
    n = len(native); n_orgs = native.org.nunique()
    entry_share = native.entry_ok.mean() * 100
    senior_share = (native.seniority == "senior").mean() * 100
    yrs_known = native[native.min_years.notna()]
    n_years = len(yrs_known)
    med_years = int(yrs_known.min_years.median()) if n_years else None
    n_manual = int((native.collection_method == "manual").sum())
    n_api = n - n_manual
    os.makedirs(SITE, exist_ok=True)

    # ---- index ----
    body = f"""
<h1>The entry-level cliff in AI safety hiring</h1>
<p class="lede">Pulled straight from the orgs' own hiring systems, today's open roles
skew sharply senior — early-career entry points are scarce.</p>
<p class="meta">Snapshot {snap} · {n} open roles across {n_orgs} mission-driven AI-safety organizations
({n_api} via public feed, {n_manual} captured by hand) · frontier labs shown separately, not blended in.</p>

<div class="stat">
  <div><div class="n">{entry_share:.0f}%</div><div class="l">of open roles are accessible early-career</div></div>
  <div><div class="n">{senior_share:.0f}%</div><div class="l">carry an explicitly senior title</div></div>
  <div><div class="n">{n_orgs}</div><div class="l">AI-safety orgs in the dataset</div></div>
</div>

<div class="callout"><b>How to read this.</b> "Entry-accessible" means the title carries an
entry marker (intern, fellow, junior, new-grad…) <i>or</i> the description states a minimum of
≤2 years' experience. It is a measure of <i>advertised, public</i> openings — not the field's
true need. Much senior and network hiring never gets posted, so if anything this understates how
hard early entry is.</div>

<div class="card">{chart_seniority(native)}</div>
<p>Across {n_orgs} mission-driven AI-safety orgs, explicitly senior titles
(Chief of Staff, Director, Principal, Head of…) outnumber entry-marked roles many times over.
Most remaining titles give no seniority signal at all.</p>

<div class="card">{chart_by_org(native)}</div>
<p>The skew isn't one organization — it holds across the orgs in the sample.</p>

<h2>Where a number is named, the floor is high</h2>
<div class="card">{chart_minyears(native)}</div>
<p>Most AIS orgs state requirements qualitatively, so only {n_years} of {n} roles name an
explicit minimum — but where they do, the median floor is <b>{med_years} years</b>, and barely any
sit at the ≤2-year level that's reachable early-career. This is a corroborating cross-check on the
title signal above, not a stand-alone claim (the sample is small and template-driven).</p>

<h2>Frontier labs look the same</h2>
<div class="card">{chart_compare(native, labs)}</div>
<p>Anthropic's public board — kept separate because most of its roles aren't safety work —
shows a near-identical early-career share, suggesting the cliff is a field-wide pattern rather
than a small-org artifact.</p>

<h2>What this is, and isn't</h2>
<p>This is a reproducible, <b>source-direct</b> snapshot: every role is pulled from the
organization's own hiring system, not a hand-curated job board. That removes the selection bias
baked into curated boards — but it covers only orgs that expose a public feed. See
<a href="coverage.html">Coverage</a> for exactly who is in and out, and
<a href="methodology.html">Method</a> for how roles are classified and where the limits are.</p>
"""
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(page(
        "The entry-level cliff in AI safety hiring", body, "index.html"))

    # ---- methodology ----
    n_years = int(native.min_years.notna().sum())
    meth = f"""
<h1>Method &amp; limitations</h1>
<h2>Where the data comes from</h2>
<p>Roles are pulled directly from each organization's hiring system: public applicant-tracking
feeds (Greenhouse, Lever, Ashby) where available, and a hand-maintained supplement for orgs whose
boards have no machine-readable feed (Airtable / Notion / custom). Every role is tagged with its
<code>collection_method</code> (<span class="tag api">api</span> or
<span class="tag manual">manual</span>) so the two are always separable. The current snapshot
({snap}) holds {n} AIS-native roles — {n_api} pulled automatically from public feeds and
{n_manual} captured by hand from four orgs whose boards are JavaScript-rendered: GovAI and Apart
server-render enough to parse directly, while Redwood and Palisade render entirely client-side and
were read with a headless browser. Every manual row is tagged so it stays separable from the
automated feed, and the <a href="coverage.html">roster</a> shows each org's method.</p>

<h2>How roles are classified</h2>
<p>Two transparent, rule-based signals, both auditable in <code>classify.py</code>:</p>
<ul>
<li><b>Title seniority</b> — explicit markers split titles into <i>entry</i> (intern, fellow,
junior, new-grad, graduate, apprentice…), <i>senior</i> (senior, staff, principal, lead, head,
director, chief, manager, founding…), or <i>unspecified</i>. An unmarked "Research Engineer"
stays <i>unspecified</i> rather than being guessed into a level.</li>
<li><b>Minimum years</b> — the smallest credibly-stated "N+ years" figure in the description.
The parser anchors on structured "Required experience" fields and year-mentions sitting next to
the word "experience", and explicitly rejects non-experience uses of "years" (visa residency,
post-employment bans, "in the next N years", etc.), each of which was producing false positives
in an earlier pass. {n_years} of {n} roles name an explicit figure; the rest state requirements
qualitatively, so this is structurally sparse and serves as a cross-check, with title seniority
remaining the primary signal.</li>
</ul>
<p>A role counts as <b>entry-accessible</b> if its title is entry-marked <i>or</i> its stated
minimum is ≤2 years.</p>

<h2>Known limitations</h2>
<ul>
<li><b>Postings ≠ need.</b> This measures publicly advertised openings. Senior and network-based
hiring often never gets posted, so the data undercounts senior demand and must not be read as
"where the field needs people most."</li>
<li><b>Partial coverage.</b> Only orgs with a reachable feed are included; the
<a href="coverage.html">roster</a> lists every org considered and its status.</li>
<li><b>Title heuristics are coarse.</b> Counting "Manager"/"Lead" as senior is defensible but
imperfect; the rules are published so you can disagree precisely.</li>
<li><b>Single snapshot.</b> This is one point in time, not yet a trend.</li>
</ul>
"""
    open(os.path.join(SITE, "methodology.html"), "w", encoding="utf-8").write(page(
        "Method & limitations", meth, "methodology.html"))

    # ---- coverage ----
    rows = ""
    with open(os.path.join(HERE, "orgs.csv"), newline="", encoding="utf-8") as f:
        for o in csv.DictReader(f):
            src = o["source"]; ident = o["identifier"]
            if o["category"] == "frontier-lab":
                tag = '<span class="tag out">comparison only</span>'
            elif ident == "PENDING":
                tag = '<span class="tag manual">pending (browser capture)</span>'
            elif ident == "manual" or src in ("airtable", "notion"):
                tag = '<span class="tag manual">included (manual)</span>'
            else:
                tag = '<span class="tag api">included (api)</span>'
            cnt = int((native.org == o["name"]).sum()) if ident != "PENDING" else ""
            rows += f"<tr><td>{o['name']}</td><td>{o['category']}</td><td>{src}</td><td>{tag}</td><td>{cnt}</td></tr>"
    cov = f"""
<h1>Coverage roster</h1>
<p>Every organization considered, its hiring-data source, and whether it's in the current
snapshot. Transparency here is the point: you can see exactly what is and isn't counted.</p>
<table><thead><tr><th>Organization</th><th>Category</th><th>Source</th><th>Status</th><th>Roles</th></tr></thead>
<tbody>{rows}</tbody></table>
<p><small>"Pending (manual)" orgs use Airtable/Notion/custom pages with no machine-readable feed
and are being added through the hand-maintained supplement. Frontier labs are shown as a
comparison only and excluded from the headline metric.</small></p>
<p>Raw snapshot: <code>data/snapshots/snapshot_{snap}.csv</code></p>
"""
    open(os.path.join(SITE, "coverage.html"), "w", encoding="utf-8").write(page(
        "Coverage roster", cov, "coverage.html"))

    print(f"Built site/ from snapshot {snap}: {n} AIS-native roles, {n_orgs} orgs.")
    print(f"  entry-accessible {entry_share:.1f}%  ·  senior-marked {senior_share:.1f}%")


if __name__ == "__main__":
    build()
