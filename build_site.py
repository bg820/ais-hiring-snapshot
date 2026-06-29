"""Build the static site from the snapshot archive.

    python build_site.py

Reads every data/snapshots/*.csv, uses the newest for the headline study and
all of them for the trends page, then writes a self-contained static site into
site/ (findings, trends, method, coverage). Re-run to regenerate everything.
"""
from __future__ import annotations
import csv
import glob
import os
import datetime as dt
import pandas as pd
import plotly.graph_objects as go

from classify import (seniority_from_title, min_years_experience,
                      is_entry_accessible, is_expression_of_interest)

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
SNAP_DIR = os.path.join(HERE, "data", "snapshots")

_gh_repo = os.environ.get("GITHUB_REPOSITORY")
REPO_URL = f"https://github.com/{_gh_repo}" if _gh_repo else "https://github.com/USERNAME/ais-hiring-snapshot"

INK = "#1a2233"; MUTE = "#5b6472"; ACCENT = "#c1452e"; SENIOR = "#9aa3b0"
ENTRY = "#2e7d57"; UNSPEC = "#d8a13a"; GRID = "#e7e9ee"


def snapshots():
    return sorted(glob.glob(os.path.join(SNAP_DIR, "*.csv")))


def prep(df):
    """Add classification columns and split frontier labs from AIS-native orgs."""
    df = df.fillna("")
    if "description" not in df.columns:
        df["description"] = ""
    df["eoi"] = df.title.map(is_expression_of_interest)
    df["seniority"] = df.title.map(seniority_from_title)
    df["min_years"] = df.description.map(min_years_experience)
    df["entry_ok"] = df.apply(lambda r: is_entry_accessible(r.title, r.description), axis=1)
    return df


def metrics(df):
    """Per-snapshot summary, computed on concrete vacancies (EOIs removed)."""
    native_all = df[df.category != "frontier-lab"]
    concrete = native_all[~native_all.eoi]
    n = len(concrete)
    return {
        "orgs": native_all.org.nunique(),
        "listings": len(native_all),
        "eoi": int(native_all.eoi.sum()),
        "concrete": n,
        "entry_pct": round(concrete.entry_ok.mean() * 100, 1) if n else 0,
        "senior_pct": round((concrete.seniority == "senior").mean() * 100, 1) if n else 0,
    }


# ---------- charts ----------
def style(fig, height):
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=height,
                      font=dict(color=INK, size=14), legend=dict(orientation="h", y=-0.18),
                      paper_bgcolor="white", plot_bgcolor="white")
    fig.update_xaxes(gridcolor=GRID); fig.update_yaxes(gridcolor=GRID)


_JS = [False]


def fig_html(fig, height=360):
    style(fig, height)
    if not _JS[0]:
        inc = True; _JS[0] = True
    else:
        inc = False
    return fig.to_html(full_html=False, include_plotlyjs=inc, config={"displayModeBar": False})


def chart_seniority(c):
    order = ["entry", "unspecified", "senior"]
    labels = {"entry": "Entry-marked", "unspecified": "Unspecified", "senior": "Senior-marked"}
    vc = c.seniority.value_counts()
    vals = [int(vc.get(k, 0)) for k in order]
    fig = go.Figure(go.Bar(x=[labels[k] for k in order], y=vals,
                           marker_color=[ENTRY, UNSPEC, SENIOR], text=vals, textposition="outside"))
    fig.update_layout(yaxis_title="Current vacancies", title="Seniority signal in job titles")
    return fig_html(fig)


def chart_by_org(c):
    piv = (c.groupby(["org", "seniority"]).size().unstack(fill_value=0)
           .reindex(columns=["entry", "unspecified", "senior"], fill_value=0))
    piv = piv.loc[piv.sum(axis=1).sort_values().index]
    fig = go.Figure()
    for k, col, name in [("senior", SENIOR, "Senior-marked"),
                         ("unspecified", UNSPEC, "Unspecified"),
                         ("entry", ENTRY, "Entry-marked")]:
        fig.add_bar(y=piv.index, x=piv[k], name=name, orientation="h", marker_color=col)
    fig.update_layout(barmode="stack", title="Vacancies by org and seniority", xaxis_title="Current vacancies")
    return fig_html(fig, height=380)


def chart_compare(c, labs):
    names = ["AIS-native orgs", "Anthropic (frontier lab)"]
    shares = [round(c.entry_ok.mean() * 100, 1) if len(c) else 0,
              round(labs.entry_ok.mean() * 100, 1) if len(labs) else 0]
    fig = go.Figure(go.Bar(x=names, y=shares, marker_color=[ACCENT, SENIOR],
                           text=[f"{s}%" for s in shares], textposition="outside"))
    fig.update_layout(yaxis_title="% of vacancies", yaxis_range=[0, max(shares + [10]) * 1.4],
                      title="Share of vacancies open to early-career applicants")
    return fig_html(fig, height=320)


def chart_trends(rows):
    dates = [r["date"] for r in rows]
    fig = go.Figure()
    fig.add_scatter(x=dates, y=[r["entry_pct"] for r in rows], name="Early-career %",
                    mode="lines+markers", line=dict(color=ENTRY, width=3))
    fig.add_scatter(x=dates, y=[r["senior_pct"] for r in rows], name="Senior %",
                    mode="lines+markers", line=dict(color=SENIOR, width=3))
    fig.update_layout(yaxis_title="% of vacancies", xaxis_title="Snapshot",
                      title="Seniority mix over time")
    return fig_html(fig, height=340)


# ---------- template ----------
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
.stat .l{font-size:13px;color:var(--mute);max-width:175px;margin-top:6px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px;margin:18px 0}
.callout{background:#fff7f4;border:1px solid #f0d2c8;border-radius:10px;padding:14px 16px;font-size:14px;color:#7a3a2c}
.roles{background:#fff;border:1px solid var(--line);border-radius:10px;padding:8px 16px;margin:16px 0}
.roles li{margin:6px 0}
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


def page(title, body, active):
    nav = ""
    for href, label in [("index.html", "Findings"), ("trends.html", "Trends"),
                        ("methodology.html", "Method"), ("coverage.html", "Coverage")]:
        style_attr = " style=color:var(--accent)" if href == active else ""
        nav += f'<a href="{href}"{style_attr}>{label}</a>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}</style></head>
<body><header class="site"><div class="wrap"><a class="brand" href="index.html">AIS Hiring Snapshot</a>
<nav>{nav}</nav></div></header><main class="wrap">{body}</main>
<footer><div>Source-direct dataset, rebuilt from public data. <a href="{REPO_URL}">Code and data</a>.
Built {dt.date.today().isoformat()}. These counts cover publicly posted vacancies only.</div></footer>
</body></html>"""


def build():
    snaps = snapshots()
    df = prep(pd.read_csv(snaps[-1]))
    snap = os.path.basename(snaps[-1]).replace("snapshot_", "").replace(".csv", "")

    native_all = df[df.category != "frontier-lab"].copy()
    concrete = native_all[~native_all.eoi].copy()
    labs = df[df.org == "Anthropic"].copy()
    labs_concrete = labs[~labs.eoi]

    n = len(concrete); n_orgs = native_all.org.nunique()
    n_eoi = int(native_all.eoi.sum())
    entry_share = concrete.entry_ok.mean() * 100
    senior_share = (concrete.seniority == "senior").mean() * 100
    senior_excl = (concrete[concrete.org != "Goodfire"].seniority == "senior").mean() * 100
    top_org = concrete.org.value_counts().index[0]
    top_share = concrete.org.value_counts(normalize=True).iloc[0] * 100

    entry_roles = concrete[concrete.entry_ok]
    entry_orgs = entry_roles.org.nunique()
    prog = entry_roles.title.str.contains("fellow|intern|resident|scholar|apprentice", case=False)
    all_programs = len(entry_roles) > 0 and bool(prog.all())

    yrs = concrete[concrete.min_years.notna()]
    n_years = len(yrs)
    med_years = int(yrs.min_years.median()) if n_years else 0
    top_years_org = yrs.org.value_counts().index[0] if n_years else ""

    n_manual = int((concrete.collection_method == "manual").sum()) if "collection_method" in concrete else 0
    n_api = n - n_manual
    os.makedirs(SITE, exist_ok=True)

    # entry-role list (kept accurate by reading from the data, not hard-coded)
    role_items = "".join(f"<li><b>{r.org}</b>: {r.title}</li>" for _, r in entry_roles.iterrows())
    program_line = ("Every one of them is a structured program rather than a standing job. "
                    "In AI safety the way in is a program, not a job posting."
                    if all_programs else
                    "Most of them are structured programs (internships and fellowships) rather than standing staff jobs.")

    # ---- Findings ----
    body = f"""
<h1>The entry-level cliff in AI safety hiring</h1>
<p class="lede">Read straight from each org's own hiring system, today's openings lean heavily
toward senior people. Ways in for someone early in their career are rare.</p>
<p class="meta">Snapshot {snap}. {n} current vacancies across {n_orgs} mission-driven AI-safety
organizations, after setting aside {n_eoi} standing "expression of interest" listings. Frontier
labs are reported separately, not mixed in.</p>

<div class="stat">
  <div><div class="n">{entry_share:.0f}%</div><div class="l">of vacancies are open to early-career applicants</div></div>
  <div><div class="n">{senior_share:.0f}%</div><div class="l">carry a senior title</div></div>
  <div><div class="n">{n_orgs}</div><div class="l">AI-safety orgs in the dataset</div></div>
</div>

<div class="callout"><b>How to read this.</b> A role counts as open to early-career applicants if
the title says intern, fellow, junior, or new grad, or the description asks for two years of
experience or less. It counts vacancies that are posted in public. A lot of senior and
network hiring never gets advertised, so if anything this view understates how hard the early
years are.</div>

<div class="card">{chart_seniority(concrete)}</div>
<p>Senior titles such as Chief of Staff, Director, Principal, and Head of outnumber entry-marked
ones by a wide margin. Most of the rest give no clear seniority signal in the title.</p>

<div class="card">{chart_by_org(concrete)}</div>
<p>The pattern is uneven across orgs, so be careful reading the totals: one organization,
{top_org}, makes up about {top_share:.0f}% of all the vacancies here, and senior roles sit at
{senior_share:.0f}% with it included versus {senior_excl:.0f}% without it. The steadier finding is
on the entry side: only {entry_orgs} of the {n_orgs} orgs post any early-career role at all.</p>

<h2>How people actually get in</h2>
<p>Here are the early-career openings in this snapshot:</p>
<ul class="roles">{role_items}</ul>
<p>{program_line}</p>

<h2>Frontier labs look similar</h2>
<div class="card">{chart_compare(concrete, labs_concrete)}</div>
<p>Anthropic's public board, kept separate because most of its roles are not safety work, shows a
similar early-career share. So the cliff is not just an effect of small orgs.</p>

<p><small>On stated experience: where a posting names a minimum, the floor sits around
{med_years} years. Only a few orgs name a number at all, and most of those come from a single org
({top_years_org}) that uses a structured template, so read it as a side note, not a field-wide
figure.</small></p>

<h2>What this is, and what it is not</h2>
<p>Every role here comes from the organization's own hiring system rather than a curated job board,
which avoids the picking-and-choosing built into those boards. It only covers orgs we could reach.
The <a href="coverage.html">coverage page</a> lists every org and how its data was collected, and
the <a href="trends.html">trends page</a> tracks these numbers as new snapshots come in.</p>
"""
    write("index.html", "The entry-level cliff in AI safety hiring", body, "index.html")

    # ---- Trends ----
    rows = []
    for s in snaps:
        m = metrics(prep(pd.read_csv(s)))
        m["date"] = os.path.basename(s).replace("snapshot_", "").replace(".csv", "")
        rows.append(m)
    trows = "".join(
        f"<tr><td>{r['date']}</td><td>{r['orgs']}</td><td>{r['concrete']}</td>"
        f"<td>{r['eoi']}</td><td>{r['entry_pct']:.0f}%</td><td>{r['senior_pct']:.0f}%</td></tr>"
        for r in rows)
    trends = f"""
<h1>Trends over time</h1>
<p class="lede">Each weekly snapshot is saved, so the same measures can be tracked as the months
go by.</p>
<p>The job runs every week and commits a fresh dated snapshot. Right now there are
{len(rows)} of them, so the lines below are still short. They will fill in on their own.</p>

<div class="card">{chart_trends(rows)}</div>

<table><thead><tr><th>Snapshot</th><th>Orgs</th><th>Vacancies</th><th>EOIs set aside</th>
<th>Early-career</th><th>Senior</th></tr></thead><tbody>{trows}</tbody></table>

<div class="callout"><b>Reading the early points.</b> Coverage grew from 8 orgs to {n_orgs} as more
orgs were added, so the first snapshots are not a like-for-like comparison with the later ones.
The series becomes a fair trend once the org list settles, from the {snap} snapshot on. Treat
anything before that as a baseline rather than a movement.</div>
"""
    write("trends.html", "Trends over time", trends, "trends.html")

    # ---- Method ----
    meth = f"""
<h1>Method and limits</h1>
<h2>Where the data comes from</h2>
<p>Roles come straight from each organization's hiring system: public applicant-tracking feeds
(Greenhouse, Lever, Ashby) where they exist, and a hand-kept supplement for orgs whose boards are
built in JavaScript. Every role is tagged with how it was collected
(<span class="tag api">api</span> or <span class="tag manual">manual</span>), so the two never
blur together. This snapshot ({snap}) holds {n} concrete vacancies, {n_api} from feeds and
{n_manual} captured by hand. Four orgs with no machine-readable feed (GovAI, Apart, Redwood,
Palisade) were read off their pages, the last two with a browser that runs the page's scripts.</p>

<h2>Expressions of interest are set aside</h2>
<p>Some listings are standing "expression of interest" or "general interest" invitations rather
than posted openings. There are {n_eoi} of them in this snapshot. They are kept in the dataset but
left out of the vacancy counts, since they are a way to register rather than a job to fill.</p>

<h2>How roles are sorted</h2>
<p>Two plain rules, both readable in <code>classify.py</code>:</p>
<ul>
<li><b>Title seniority.</b> Clear markers sort titles into <i>entry</i> (intern, fellow, junior,
new grad, graduate, apprentice), <i>senior</i> (senior, staff, principal, lead, head, director,
chief, manager, founding), or <i>unspecified</i>. An unmarked "Research Engineer" stays
unspecified rather than getting a guessed level.</li>
<li><b>Minimum years.</b> The smallest stated "N years" figure in the description, used as a floor.
The parser anchors on structured "required experience" fields and on year-mentions that sit next
to the word experience, and skips the non-experience uses of "years" (visa residency, post-job
bans, "in the next N years"). Only {n_years} of {n} roles state a number, so it is a cross-check;
the title remains the main signal.</li>
</ul>

<h2>What to keep in mind</h2>
<ul>
<li><b>Postings are not need.</b> This counts public openings. Senior and network hiring often
never gets posted, so the data undercounts senior demand and should not be read as where the field
most needs people.</li>
<li><b>One org carries a lot of weight.</b> {top_org} is about {top_share:.0f}% of the vacancies,
so it pulls the field-wide numbers toward its own shape.</li>
<li><b>Partial coverage.</b> Only orgs we could reach are in. The <a href="coverage.html">roster</a>
shows who is in and who is out.</li>
<li><b>Coarse title rules.</b> Counting "Manager" or "Lead" as senior is a judgment call. The
rules are written down so anyone can disagree with a specific case.</li>
</ul>
"""
    write("methodology.html", "Method and limits", meth, "methodology.html")

    # ---- Coverage ----
    counts = native_all.org.value_counts()
    rows_html = ""
    with open(os.path.join(HERE, "orgs.csv"), newline="", encoding="utf-8") as f:
        for o in csv.DictReader(f):
            src = o["source"]; ident = o["identifier"]
            if o["category"] == "frontier-lab":
                tag = '<span class="tag out">comparison only</span>'
            elif ident == "PENDING":
                tag = '<span class="tag manual">pending</span>'
            elif ident == "manual" or src in ("airtable", "notion", "custom"):
                tag = '<span class="tag manual">included (manual)</span>'
            else:
                tag = '<span class="tag api">included (api)</span>'
            cnt = int(counts.get(o["name"], 0)) if ident != "PENDING" else ""
            rows_html += (f"<tr><td>{o['name']}</td><td>{o['category']}</td><td>{src}</td>"
                          f"<td>{tag}</td><td>{cnt}</td></tr>")
    cov = f"""
<h1>Coverage roster</h1>
<p>Every organization considered, where its hiring data comes from, and whether it is in the
current snapshot. The point of this page is that you can see exactly what is and is not counted.</p>
<table><thead><tr><th>Organization</th><th>Category</th><th>Source</th><th>Status</th>
<th>Listings</th></tr></thead><tbody>{rows_html}</tbody></table>
<p><small>Listings counts include expressions of interest; the findings and trends pages report
concrete vacancies only. Frontier labs are shown for comparison and left out of the headline
numbers.</small></p>
<p>Raw snapshot: <code>data/snapshots/snapshot_{snap}.csv</code></p>
"""
    write("coverage.html", "Coverage roster", cov, "coverage.html")

    print(f"Built site from {snap}: {n} vacancies ({n_eoi} EOIs set aside), {n_orgs} orgs.")
    print(f"  early-career {entry_share:.1f}%  senior {senior_share:.1f}%  (senior excl {top_org} {senior_excl:.1f}%)")
    print(f"  trends points: {len(rows)}")


def write(name, title, body, active):
    with open(os.path.join(SITE, name), "w", encoding="utf-8") as f:
        f.write(page(title, body, active))


if __name__ == "__main__":
    build()
