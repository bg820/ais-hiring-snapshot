"""Build the static site from the snapshot archive and the hand audit.

    python build_site.py

Reads every data/snapshots/*.csv and the newest audit/hand_labels_*.csv, then
writes a self-contained static site into site/:

    index.html        the findings, anchored to the most recent audited snapshot
    roles.html        every current vacancy, filterable (newest snapshot)
    trends.html       the like-for-like series across all snapshots
    methodology.html  sources, rules, the audit, limits and corrections
    coverage.html     every org considered, in or out, and why

No charting library: charts are plain HTML and inline SVG, so each page is a
few dozen kilobytes and follows the reader's light or dark setting.
"""
from __future__ import annotations
import csv
import glob
import html
import json
import os
import re
import shutil
import datetime as dt

import pandas as pd

import classify
from classify import (seniority_from_title, min_years_experience, is_entry_accessible,
                      is_expression_of_interest, function_of, says_open_below_senior)

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
SNAP_DIR = os.path.join(HERE, "data", "snapshots")
AUDIT_DIR = os.path.join(HERE, "audit")

_gh_repo = os.environ.get("GITHUB_REPOSITORY") or "bg820/ais-hiring-snapshot"
REPO_URL = f"https://github.com/{_gh_repo}"

# Orgs recorded under an older name in earlier snapshots.
ALIASES = {"UK AI Safety Institute": "UK AI Security Institute"}

OPEN, UNCLEAR, CLOSED = "open", "unclear", "closed"
BANDS = [OPEN, UNCLEAR, CLOSED]
BAND_LABEL = {OPEN: "Open to early-career", UNCLEAR: "Doesn't say",
              CLOSED: "Needs more experience"}
TECHNICAL = {"Research", "Engineering & product", "Security & IT"}
FRONTIER = "Anthropic"

esc = html.escape


# ---------- data ----------
def read_orgs():
    with open(os.path.join(HERE, "orgs.csv"), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


ORGS = read_orgs()
ORG_TYPE = {o["name"]: o["org_type"] for o in ORGS}


def snapshots():
    return sorted(glob.glob(os.path.join(SNAP_DIR, "snapshot_*.csv")))


def snap_date(path):
    return re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path)).group(1)


def rule_band(r):
    """The rules' three-way reading, on the same scale as the hand audit."""
    if r.open_rule:
        return OPEN
    if r.level == "senior" or (r.years is not None and r.years > 2):
        return CLOSED
    return UNCLEAR


def load(path):
    df = pd.read_csv(path, dtype=str).fillna("")
    df["org"] = df.org.replace(ALIASES)
    df["org_type"] = df.org.map(ORG_TYPE).fillna("")
    if "collection_method" not in df:
        df["collection_method"] = "api"
    df["native"] = df.category != "frontier-lab"
    df["eoi"] = df.title.map(is_expression_of_interest)
    df["level"] = df.title.map(seniority_from_title)
    df["years"] = df.description.map(min_years_experience).astype(object)
    df["years"] = df.years.where(df.years.notna(), None)
    df["open_rule"] = [is_entry_accessible(t, d) for t, d in zip(df.title, df.description)]
    df["open_text"] = df.description.map(says_open_below_senior)
    df["function"] = [function_of(t, d) for t, d in zip(df.title, df.department)]
    df["rule_band"] = df.apply(rule_band, axis=1)
    return df


def latest_audit():
    files = sorted(glob.glob(os.path.join(AUDIT_DIR, "hand_labels_*.csv")))
    if not files:
        return None, None
    path = files[-1]
    return path, snap_date(path)


def pct(n, d):
    return 100.0 * n / d if d else 0.0


def fmt_pct(x):
    return f"{x:.0f}%"


WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
         8: "eight", 9: "nine", 10: "ten"}


def word(n):
    return WORDS.get(n, str(n))


def one_in(p):
    """0.183 -> 'Fewer than one in five'; 0.26 -> 'About one in four'."""
    if p <= 0:
        return "None of the"
    n = max(1, round(1 / p))
    return (f"Fewer than one in {word(n)}" if p < 1 / n - 0.005
            else f"About one in {word(n)}")


def human_date(d):
    return dt.date.fromisoformat(d).strftime("%-d %B %Y")


def band_counts(frame, col):
    vc = frame[col].value_counts()
    return {b: int(vc.get(b, 0)) for b in BANDS}


# ---------- chart pieces ----------
def legend(counts=None):
    items = []
    for b in BANDS:
        n = f' <span class="lg-n">{counts[b]}</span>' if counts else ""
        items.append(f'<span class="lg"><i class="sw b-{b}"></i>{BAND_LABEL[b]}{n}</span>')
    return f'<div class="legend">{"".join(items)}</div>'


def waffle(frame, col):
    """One square per vacancy, grouped open -> doesn't say -> needs more."""
    order = {b: i for i, b in enumerate(BANDS)}
    f = frame.assign(_o=frame[col].map(order)).sort_values(["_o", "org", "title"])
    cells = []
    for _, r in f.iterrows():
        tip = f"{r.org}\n{r.title}\n{BAND_LABEL[r[col]]}"
        if col == "hand_label" and r.get("evidence"):
            tip += f": {r.evidence}"
        cells.append(f'<i class="cell b-{r[col]}" data-tip="{esc(tip)}"></i>')
    return f'<div class="waffle" role="img" aria-label="{len(f)} vacancies">{"".join(cells)}</div>'


def stacked_rows(groups, col, label_width="11.5rem"):
    """Horizontal stacked bars, one per group, length proportional to size."""
    rows = []
    biggest = max((len(g) for _, g in groups), default=1)
    for name, g in groups:
        c = band_counts(g, col)
        n = len(g)
        segs = "".join(
            f'<span class="seg b-{b}" style="flex:{c[b]}" '
            f'data-tip="{esc(name)}\n{BAND_LABEL[b]}: {c[b]} of {n}"></span>'
            for b in BANDS if c[b])
        rows.append(
            f'<div class="srow"><div class="sl">{esc(name)}</div>'
            f'<div class="strack"><div class="sbar" style="width:{100 * n / biggest:.1f}%">{segs}</div>'
            f'<span class="sn">{n}<span class="so">{" · " + str(c[OPEN]) + " open" if c[OPEN] else ""}</span></span></div></div>')
    return f'<div class="stacked" style="--lw:{label_width}">{"".join(rows)}</div>'


def data_table(headers, rows, caption="Show the numbers"):
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return (f'<details class="dt"><summary>{esc(caption)}</summary>'
            f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div></details>')


def line_chart(dates, series, ymax, yfmt, ylabel, marks=()):
    """Inline SVG line chart. series: [(name, values, css-var)], one y axis."""
    W, H, L, R, T, B = 560, 250, 44, 118, 14, 34
    pw, ph = W - L - R, H - T - B
    n = len(dates)
    x = lambda i: L + (pw * i / (n - 1) if n > 1 else pw / 2)
    y = lambda v: T + ph - ph * (v / ymax if ymax else 0)
    step = ymax / 4
    out = [f'<svg class="lc" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(ylabel)}">']
    for k in range(5):
        v = step * k
        out.append(f'<line class="grid" x1="{L}" x2="{L + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text class="tick" x="{L - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{yfmt(v)}</text>')
    seen = set()
    for i, d in enumerate(dates):
        m = d[:7]
        if m not in seen:
            seen.add(m)
            out.append(f'<text class="tick" x="{x(i):.1f}" y="{H - 10}" text-anchor="middle">'
                       f'{dt.date.fromisoformat(d).strftime("%b")}</text>')
    for d, text in marks:
        if d in dates:
            i = dates.index(d)
            out.append(f'<line class="mark" x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{T}" y2="{T + ph}"/>'
                       f'<text class="mtext" x="{x(i) - 4:.1f}" y="{T + 10}" text-anchor="end">{esc(text)}</text>')
    ends = []
    for name, vals, var in series:
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        out.append(f'<polyline class="ln" style="stroke:var({var})" points="{pts}"/>')
        ends.append((y(vals[-1]), name, vals[-1], var))
    # end labels, nudged apart only enough not to overlap
    ends.sort()
    placed = []
    for yy, name, v, var in ends:
        ly = max(yy, placed[-1] + 16) if placed else yy
        placed.append(ly)
        out.append(f'<circle class="dot" cx="{x(n - 1):.1f}" cy="{yy:.1f}" r="4" style="fill:var({var})"/>'
                   f'<text class="elab" x="{x(n - 1) + 10:.1f}" y="{ly + 4:.1f}">{esc(name)} {yfmt(v)}</text>')
    # hover columns
    half = pw / (n - 1) / 2 if n > 1 else pw / 2
    for i, d in enumerate(dates):
        tip = human_date(d) + "".join(f"\n{nm}: {yfmt(vals[i])}" for nm, vals, _ in series)
        out.append(f'<rect class="hit" x="{x(i) - half:.1f}" y="{T}" width="{2 * half:.1f}" '
                   f'height="{ph}" data-tip="{esc(tip)}"/>')
    out.append("</svg>")
    return "".join(out)


# ---------- page shell ----------
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&display=swap" rel="stylesheet">')

CSS = """
:root{--plane:#f7f6f2;--surface:#fcfcfb;--ink:#141413;--ink-2:#4f4e4a;--muted:#6e6d67;
--line:#e4e3dc;--axis:#c3c2b7;--link:#1c5cab;--open:#2a78d6;--closed:#7b7a73;--unclear:#cfcec6;
--wash:#eef3fb;--ring:rgba(20,20,19,.10);color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--plane:#0f0f0e;--surface:#1a1a19;
--ink:#f4f3ee;--ink-2:#c9c8bf;--muted:#9a998f;--line:#2c2c2a;--axis:#44443f;--link:#86b6ef;--open:#3987e5;
--closed:#a3a299;--unclear:#4a4a45;--wash:#16233a;--ring:rgba(255,255,255,.10);color-scheme:dark}}
:root[data-theme="dark"]{--plane:#0f0f0e;--surface:#1a1a19;--ink:#f4f3ee;--ink-2:#c9c8bf;--muted:#9a998f;
--line:#2c2c2a;--axis:#44443f;--link:#86b6ef;--open:#3987e5;--closed:#a3a299;--unclear:#4a4a45;
--wash:#16233a;--ring:rgba(255,255,255,.10);color-scheme:dark}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--plane);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--link);text-underline-offset:2px}
.wrap{max-width:760px;margin:0 auto;padding:0 16px}
header.site{border-bottom:1px solid var(--line)}
header.site .wrap{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:center;justify-content:space-between;padding-top:14px;padding-bottom:14px}
.brand{font-weight:650;color:var(--ink);text-decoration:none;font-size:15px;letter-spacing:-.01em}
.brand b{color:var(--open);font-weight:650}
nav{display:flex;flex-wrap:wrap;gap:4px 16px;align-items:center}
nav a{color:var(--ink-2);text-decoration:none;font-size:14px;padding:2px 0;border-bottom:2px solid transparent}
nav a:hover{color:var(--ink)}nav a.on{color:var(--ink);border-bottom-color:var(--open)}
#theme{background:none;border:1px solid var(--line);color:var(--ink-2);border-radius:999px;font:inherit;font-size:12px;padding:2px 10px;cursor:pointer}
h1,h2,h3{font-family:"Source Serif 4",Georgia,serif;font-weight:600;letter-spacing:-.01em;line-height:1.2}
h1{font-size:clamp(30px,5.4vw,44px);margin:36px 0 14px}
h2{font-size:clamp(22px,3.4vw,27px);margin:52px 0 10px}
h3{font-size:19px;margin:28px 0 6px}
.kicker{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:32px 0 -18px}
.lede{font-size:clamp(17px,2.4vw,19px);color:var(--ink-2);margin:0 0 8px}
.meta{font-size:13px;color:var(--muted)}
p,li{max-width:68ch}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:28px 0}
.stat{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px 16px}
.stat .v{font-size:34px;font-weight:650;line-height:1.05;letter-spacing:-.02em}
.stat .v.o{color:var(--open)}
.stat .l{font-size:13px;color:var(--ink-2);margin-top:6px;line-height:1.35}
.fig{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:18px;margin:22px 0}
.fig h3{margin:0 0 2px;font-size:17px}.fig .sub{font-size:13px;color:var(--muted);margin:0 0 14px}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--ink-2);margin:0 0 12px}
.lg{display:inline-flex;align-items:center;gap:6px}.lg-n{color:var(--muted)}
.sw{width:12px;height:12px;border-radius:3px;display:inline-block}
.b-open{background:var(--open)}.b-unclear{background:var(--unclear)}.b-closed{background:var(--closed)}
.waffle{display:grid;grid-template-columns:repeat(auto-fill,minmax(15px,1fr));gap:4px}
.cell{aspect-ratio:1;border-radius:3px;display:block;cursor:default}
.cell:hover{outline:2px solid var(--ink);outline-offset:1px}
.stacked{display:flex;flex-direction:column;gap:7px}
.srow{display:grid;grid-template-columns:var(--lw) 1fr;gap:12px;align-items:center;font-size:14px}
.sl{color:var(--ink-2);text-align:right;line-height:1.25}
.strack{display:flex;align-items:center;gap:8px;min-width:0}
.sbar{display:flex;gap:2px;height:18px;min-width:6px}
.seg{display:block;height:100%}.seg:last-child{border-radius:0 4px 4px 0}
.seg:hover{filter:brightness(1.12)}
.sn{font-size:13px;color:var(--ink-2);white-space:nowrap;font-variant-numeric:tabular-nums}.so{color:var(--muted)}
@media (max-width:560px){.srow{grid-template-columns:1fr;gap:3px}.sl{text-align:left}}
.lc{width:100%;height:auto;display:block;overflow:visible}
.lc .grid{stroke:var(--line);stroke-width:1}.lc .tick{fill:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.lc .ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.lc .dot{stroke:var(--surface);stroke-width:2}.lc .elab{fill:var(--ink-2);font-size:12.5px}
.lc .mark{stroke:var(--axis);stroke-width:1}.lc .mtext{fill:var(--muted);font-size:11px}
.lc .hit{fill:transparent}.lc .hit:hover{fill:var(--ink);fill-opacity:.05}
.note{background:var(--surface);border:1px solid var(--ring);border-left:3px solid var(--open);border-radius:8px;padding:12px 16px;font-size:15px;color:var(--ink-2);margin:20px 0}
.note b{color:var(--ink)}
blockquote{margin:16px 0;padding:0 0 0 16px;border-left:2px solid var(--line);color:var(--ink-2)}
blockquote cite{display:block;font-style:normal;font-size:13px;color:var(--muted);margin-top:2px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14px;margin:10px 0}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12.5px;text-transform:uppercase;letter-spacing:.04em}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr.hl td{background:var(--wash)}
details.dt{margin-top:14px;font-size:14px}details.dt summary{cursor:pointer;color:var(--ink-2)}
.tag{display:inline-block;font-size:11.5px;line-height:1.5;padding:1px 8px;border-radius:999px;border:1px solid var(--line);color:var(--ink-2);white-space:nowrap}
.tag.o{border-color:transparent;background:var(--open);color:#fff}
code{font-size:13.5px;background:var(--surface);border:1px solid var(--line);border-radius:4px;padding:0 5px}
#tip{position:fixed;pointer-events:none;z-index:10;background:var(--ink);color:var(--plane);font-size:12.5px;line-height:1.4;padding:7px 10px;border-radius:6px;max-width:280px;white-space:pre-line;opacity:0;transition:opacity .08s}
footer{border-top:1px solid var(--line);margin-top:64px;padding:22px 0 40px;color:var(--muted);font-size:13px}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:18px 0 8px}
.filters input[type=search],.filters select{font:inherit;font-size:14px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);min-width:0}
.filters input[type=search]{flex:1 1 200px}
.filters label{font-size:14px;color:var(--ink-2);display:inline-flex;gap:6px;align-items:center}
#count{font-size:13px;color:var(--muted);margin:4px 0 0}
.roles td:first-child{white-space:nowrap}
.roles a{text-decoration:none}.roles a:hover{text-decoration:underline}
.small{font-size:13px;color:var(--muted)}
@media (max-width:560px){.roles thead{display:none}.roles tr{display:block;padding:10px 0;border-bottom:1px solid var(--line)}
.roles td{display:block;border:0;padding:1px 0}.roles td:first-child{font-size:12.5px;color:var(--muted)}
.roles td:nth-child(3){display:none}.roles td:last-child{padding-top:5px}}
"""

JS = r"""
(function(){
  var t=document.createElement('div');t.id='tip';document.body.appendChild(t);
  function place(e){var x=e.clientX+14,y=e.clientY+14,r=t.getBoundingClientRect();
    if(x+r.width>innerWidth-8)x=e.clientX-r.width-14; if(y+r.height>innerHeight-8)y=e.clientY-r.height-14;
    t.style.left=x+'px';t.style.top=y+'px';}
  document.addEventListener('pointerover',function(e){var el=e.target.closest('[data-tip]');
    if(!el){t.style.opacity=0;return;} t.textContent=el.getAttribute('data-tip');t.style.opacity=1;place(e);});
  document.addEventListener('pointermove',function(e){if(t.style.opacity==1)place(e);});
  document.addEventListener('scroll',function(){t.style.opacity=0;},{passive:true});
  var b=document.getElementById('theme'),root=document.documentElement;
  function cur(){return root.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');}
  function label(){if(b)b.textContent=cur()==='dark'?'Light':'Dark';}
  label();
  if(b)b.addEventListener('click',function(){var n=cur()==='dark'?'light':'dark';root.setAttribute('data-theme',n);
    try{localStorage.setItem('theme',n);}catch(_){} label();});
})();
"""

HEAD_JS = "try{var s=localStorage.getItem('theme');if(s)document.documentElement.setAttribute('data-theme',s);}catch(_){}"

NAV = [("index.html", "Findings"), ("roles.html", "Open roles"), ("trends.html", "Trends"),
       ("methodology.html", "Method"), ("coverage.html", "Coverage")]


def page(title, desc, body, active, extra_js=""):
    nav = "".join(f'<a href="{h}"{" class=on" if h == active else ""}>{l}</a>' for h, l in NAV)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<script>{HEAD_JS}</script>{FONTS}<style>{CSS}</style></head>
<body><header class="site"><div class="wrap"><a class="brand" href="index.html">AI Safety <b>Hiring</b> Snapshot</a>
<nav>{nav}<button id="theme" type="button" aria-label="Switch colour theme">Dark</button></nav></div></header>
<main class="wrap">{body}</main>
<footer><div class="wrap">Read straight from each organization's own hiring system and rebuilt every week.
Counts cover publicly posted vacancies only. <a href="{REPO_URL}">Code and data</a> ·
rebuilt {human_date(dt.date.today().isoformat())}.</div></footer>
<script>{JS}</script>{extra_js}</body></html>"""


def write(name, content):
    with open(os.path.join(SITE, name), "w", encoding="utf-8") as f:
        f.write(content)


# ---------- build ----------
def build():
    snaps = snapshots()
    latest_path = snaps[-1]
    latest_date = snap_date(latest_path)
    latest = load(latest_path)

    audit_path, audit_date = latest_audit()
    audit_snap = os.path.join(SNAP_DIR, f"snapshot_{audit_date}.csv")
    a_all = load(audit_snap)
    labels = pd.read_csv(audit_path, dtype=str).fillna("")
    a = a_all[a_all.native & ~a_all.eoi].merge(
        labels[["org", "title", "ext_id", "hand_label", "evidence"]],
        on=["org", "title", "ext_id"], how="left")
    missing = int(a.hand_label.eq("").sum() + a.hand_label.isna().sum())
    if missing:
        raise SystemExit(f"{missing} audited-snapshot vacancies have no hand label")

    os.makedirs(os.path.join(SITE, "data"), exist_ok=True)
    shutil.copy(audit_path, os.path.join(SITE, "data", os.path.basename(audit_path)))
    shutil.copy(latest_path, os.path.join(SITE, "data", os.path.basename(latest_path)))

    ctx = findings(a, a_all, audit_date, latest, latest_date)
    roles_page(latest, latest_date, labels)
    trends_page(snaps)
    method_page(a, a_all, audit_date, audit_path, latest, latest_date, ctx)
    coverage_page(latest, latest_date)
    print(f"Built site: audited snapshot {audit_date} ({len(a)} vacancies, "
          f"{ctx['orgs']} orgs), newest snapshot {latest_date}.")
    print(f"  hand audit  open {ctx['p_open']:.1f}%  unclear {ctx['p_unclear']:.1f}%  closed {ctx['p_closed']:.1f}%")
    print(f"  rules       open {ctx['p_rule']:.1f}%   title-only {ctx['p_title']:.1f}%")


def findings(a, a_all, audit_date, latest, latest_date):
    n = len(a)
    orgs = a.org.nunique()
    c = band_counts(a, "hand_label")
    p_open, p_unclear, p_closed = (pct(c[b], n) for b in BANDS)
    n_eoi = int((a_all.native & a_all.eoi).sum())

    title_open = int((a.level == "entry").sum())
    open_rows = a[a.hand_label == OPEN]
    open_by_title = int((open_rows.level == "entry").sum())
    open_in_text = len(open_rows) - open_by_title
    p_title = pct(title_open, n)
    p_rule = pct(int(a.open_rule.sum()), n)

    # function and org breakdowns
    fn = [(k, g) for k, g in a.groupby("function")]
    fn.sort(key=lambda kg: -len(kg[1]))
    fn_stats = sorted(((k, pct((g.hand_label == OPEN).sum(), len(g)), len(g)) for k, g in fn
                       if len(g) >= 8), key=lambda s: -s[1])
    orgs_g = sorted(((k, g) for k, g in a.groupby("org")), key=lambda kg: (-len(kg[1]), kg[0]))
    with_open = [(k, int((g.hand_label == OPEN).sum())) for k, g in orgs_g]
    n_orgs_open = sum(1 for _, k in with_open if k)
    top_open = sorted([w for w in with_open if w[1]], key=lambda w: -w[1])

    tech = a[a.function.isin(TECHNICAL)]
    nontech = a[~a.function.isin(TECHNICAL)]

    # robustness under other boundaries
    scopes = [
        ("All AI-safety orgs (the headline)", a),
        ("Nonprofits and government only", a[a.org_type.isin(["nonprofit", "government"])]),
        ("Safety companies only", a[a.org_type == "company"]),
        (f"Without {a.org.value_counts().index[0]}, the largest board",
         a[a.org != a.org.value_counts().index[0]]),
        ("Without sales and marketing roles", a[a.function != "Go-to-market"]),
        ("Technical roles only", tech),
        ("Non-technical roles only", nontech),
    ]
    rob_rows = []
    for i, (name, g) in enumerate(scopes):
        cc = band_counts(g, "hand_label")
        m = len(g)
        rob_rows.append((i, name, m, pct(cc[OPEN], m), pct(cc[UNCLEAR], m), pct(cc[CLOSED], m),
                         pct(cc[OPEN] + cc[UNCLEAR], m)))
    boundary = [r for r in rob_rows[:5] if r[2] >= 20]
    lo, hi = min(r[3] for r in boundary), max(r[3] for r in boundary)

    # frontier comparison (rules on both sides, so like is compared with like)
    labs = a_all[(a_all.org == FRONTIER) & ~a_all.eoi]
    p_lab = pct(int(labs.open_rule.sum()), len(labs))
    lab_fellows = int(labs.title.str.contains("fellow", case=False).sum())
    lab_open = int(labs.open_rule.sum())

    # quotes: the clearest body-text open doors in the audit
    quote_src = [("UK AI Security Institute", "open to hires at junior"),
                 ("Apollo Research", "require a formal background"),
                 ("FAR.AI", "without industrial experience")]
    quotes = []
    for org, needle in quote_src:
        rows = a[(a.org == org) & a.description.str.contains(needle, case=False, regex=False)]
        if len(rows):
            r = rows.iloc[0]
            d = re.sub(r"\s+", " ", r.description)
            i = d.lower().find(needle.lower())
            s = d.rfind(". ", 0, i) + 2 if d.rfind(". ", 0, i) != -1 else 0
            e = d.find(".", i)
            q = re.sub(r"^(?:[A-Z][A-Z'’&-]+\s+)+(?=[A-Z][a-z])", "", d[s:e + 1].strip())
            quotes.append((q, f"{r.org}, {r.title}"))

    ctx = dict(orgs=orgs, n=n, p_open=p_open, p_unclear=p_unclear, p_closed=p_closed,
               p_rule=p_rule, p_title=p_title, c=c)

    headline = f"{one_in(p_open / 100)} AI safety vacancies are open to someone starting out"
    live = ""
    if latest_date != audit_date:
        ln = latest[latest.native & ~latest.eoi]
        live = (f'<div class="note"><b>Newest snapshot, {human_date(latest_date)}:</b> '
                f'{len(ln)} vacancies at {ln.org.nunique()} orgs, of which the rules flag '
                f'{fmt_pct(pct(int(ln.open_rule.sum()), len(ln)))} as open to early-career applicants. '
                f'The figures below come from the last hand-checked snapshot. '
                f'<a href="roles.html">Browse the current roles.</a></div>')

    fn_rows = [(esc(k), len(g), band_counts(g, "hand_label")[OPEN],
                band_counts(g, "hand_label")[UNCLEAR], band_counts(g, "hand_label")[CLOSED]) for k, g in fn]
    org_rows = [(esc(k), len(g), band_counts(g, "hand_label")[OPEN],
                 band_counts(g, "hand_label")[UNCLEAR], band_counts(g, "hand_label")[CLOSED]) for k, g in orgs_g]
    num_head = ["", "Vacancies", "Open", "Doesn't say", "Needs more"]

    best_fn, worst_fn = fn_stats[0], fn_stats[-1]
    res = a[a.function == "Research"]
    p_res = pct((res.hand_label == OPEN).sum(), len(res))
    research_line = (f" Research, often assumed to be the hardest door, is open {fmt_pct(p_res)} of the time, "
                     "above the overall rate, largely because several labs state plainly that they hire "
                     "researchers at every level." if len(res) >= 8 and p_res > p_open else "")
    lab_line = ("The AI safety organizations are, if anything, easier to get into than the lab."
                if p_lab < p_rule else
                "By this measure the lab is at least as open as the AI safety organizations.")
    top_names = ", ".join(f"{k} ({v})" for k, v in top_open[:4])
    share_top = pct(sum(v for _, v in top_open[:4]), c[OPEN])

    rob_html = "".join(
        f'<tr{" class=hl" if i == 0 else ""}><td>{esc(name)}</td><td class="n">{m}</td>'
        f'<td class="n">{fmt_pct(po)}</td><td class="n">{fmt_pct(pu)}</td><td class="n">{fmt_pct(pc)}</td>'
        f'<td class="n">{fmt_pct(po)}–{fmt_pct(pmax)}</td></tr>'
        for i, name, m, po, pu, pc, pmax in rob_rows)

    q_html = "".join(f"<blockquote>“{esc(q)}”<cite>{esc(src)}</cite></blockquote>" for q, src in quotes)

    body = f"""
<p class="kicker">Hand-checked snapshot · {human_date(audit_date)}</p>
<h1>{esc(headline)}</h1>
<p class="lede">We read every one of the {n} vacancies currently posted by {orgs} AI safety organizations,
taken straight from their own hiring systems. By the postings' own words, {c[OPEN]} are open to someone with
two years of experience or less. {c[CLOSED]} are not. The other {c[UNCLEAR]} don't say.</p>
<p class="meta">{n_eoi} standing "expression of interest" listings are left out, since they invite
people to register rather than fill a job. Anthropic is kept separate as a comparison.</p>
{live}
<div class="stats">
  <div class="stat"><div class="v o">{fmt_pct(p_open)}</div><div class="l">open to early-career applicants</div></div>
  <div class="stat"><div class="v">{fmt_pct(p_closed)}</div><div class="l">ask for more experience or seniority</div></div>
  <div class="stat"><div class="v">{fmt_pct(p_unclear)}</div><div class="l">don't say either way</div></div>
  <div class="stat"><div class="v">{orgs}</div><div class="l">organizations, each read from its own hiring system</div></div>
</div>

<div class="fig">
<h3>Every square is one current vacancy</h3>
<p class="sub">Hover a square for the role and the line in the posting that decided it.</p>
{legend(c)}
{waffle(a, "hand_label")}
</div>

<p>"Open" is a deliberately modest bar. It means the posting itself makes room for someone early in their
career: an intern, associate or junior level, a stated floor of two years or less, or a plain statement
that junior or self-taught applicants are welcome. It does not mean beginners actually get hired. If every
"doesn't say" posting turned out to be open too, the share would reach {fmt_pct(p_open + p_unclear)}, so
that is the ceiling. The <a href="methodology.html#audit">method page</a> gives the exact rules.</p>

<h2>The way in is mostly in the small print</h2>
<p>Only {open_by_title} of the {c[OPEN]} open roles say so in the title. The other {open_in_text} say it
in the body of the posting, often in a single sentence:</p>
{q_html}
<p>So anyone skimming titles sees a much steeper cliff than the real one. That includes any analysis
that counts title keywords, as this site did until September 2026. Titles alone flag
{fmt_pct(p_title)} of these vacancies as early-career, against the {fmt_pct(p_open)} found by reading them.
If you are early in your career, read the requirements, not the title.</p>

<h2>Which kinds of work have a way in</h2>
<div class="fig">
<h3>Vacancies by kind of work</h3>
<p class="sub">Bar length is the number of vacancies; colour is what the posting asks for.</p>
{legend()}
{stacked_rows(fn, "hand_label")}
{data_table(num_head, fn_rows)}
</div>
<p>Among the larger groups, {esc(best_fn[0].lower())} has the widest door ({fmt_pct(best_fn[1])} open) and
{esc(worst_fn[0].lower())} the narrowest ({fmt_pct(worst_fn[1])}). Split more simply,
{fmt_pct(pct((tech.hand_label == OPEN).sum(), len(tech)))} of technical roles are open against
{fmt_pct(pct((nontech.hand_label == OPEN).sum(), len(nontech)))} of non-technical ones.{research_line}</p>

<h2>Which organizations have a way in</h2>
<div class="fig">
<h3>Vacancies by organization</h3>
<p class="sub">Every organization with at least one current vacancy.</p>
{legend()}
{stacked_rows(orgs_g, "hand_label", "10.5rem")}
{data_table(num_head, org_rows)}
</div>
<p>{n_orgs_open} of the {orgs} organizations have at least one open role, and {fmt_pct(share_top)} of all
open roles sit at four of them: {esc(top_names)}. The biggest boards are not the most open ones, so the field-wide
share depends heavily on which organizations are counted. That is why the next check matters.</p>

<h2>Does the finding survive a different boundary?</h2>
<p>Which organizations count as "AI safety" is a judgment call, so here is the same measure under
other reasonable boundaries. The last column runs from the open share to the ceiling, where every
"doesn't say" is counted as open.</p>
<div class="tw"><table>
<thead><tr><th>Scope</th><th class="n">Vacancies</th><th class="n">Open</th><th class="n">Doesn't say</th>
<th class="n">Needs more</th><th class="n">Range</th></tr></thead><tbody>{rob_html}</tbody></table></div>
<p>Across the boundaries of the first five rows the open share stays between {fmt_pct(lo)} and {fmt_pct(hi)}.
The finding does not hinge on one organization or one definition.</p>

<h2>A frontier lab, for comparison</h2>
<p>Anthropic's public board is far larger ({len(labs)} vacancies) and mostly not safety work, so it is kept out
of every figure above. Measured by the same rules, since it has not been hand-checked,
{fmt_pct(p_lab)} of its vacancies are open to early-career applicants ({lab_open} roles, {lab_fellows} of them
Fellows Program tracks), against {fmt_pct(p_rule)} at the AI safety organizations. {lab_line}</p>

<h2>What this can and cannot tell you</h2>
<ul>
<li><b>Postings are not the whole market.</b> Much senior hiring, and some junior hiring, happens through
networks and never gets posted. This measures advertised demand, not where the field most needs people.</li>
<li><b>Programs are mostly outside the frame.</b> Fellowships such as MATS, SPAR and GovAI's seasonal fellowships
are the main early-career route into the field, and most run on their own application cycles rather than
through a hiring system. When one appears as a posting it is counted; the rest are not.</li>
<li><b>"Open" is what the posting permits, not who gets hired.</b> A role open to juniors may still go to
someone senior.</li>
<li><b>Coverage is partial.</b> {orgs} organizations with a readable hiring system are included. The
<a href="coverage.html">coverage page</a> lists everyone considered and why each is in or out.</li>
<li><b>One reading.</b> The labels come from one careful pass through each posting. Every label and the line
behind it is in the <a href="data/{os.path.basename(latest_audit()[0])}">audit file</a>, so you can disagree
with any of them.</li>
</ul>
"""
    write("index.html", page(
        "AI Safety Hiring Snapshot",
        f"{fmt_pct(p_open)} of current AI safety vacancies are open to early-career applicants, from {n} postings "
        f"at {orgs} organizations, each read in full.", body, "index.html"))
    return ctx


def roles_page(latest, latest_date, labels):
    """Every current vacancy at the AI-safety orgs, filterable in the browser."""
    lab = {(r.org, r.title, r.ext_id): r.hand_label for r in labels.itertuples()}
    df = latest[latest.native].copy()
    items = []
    for r in df.itertuples():
        hand = lab.get((r.org, r.title, r.ext_id), "")
        band = hand or r.rule_band
        items.append({"o": r.org, "t": r.title, "f": r.function, "b": band,
                      "h": 1 if hand else 0, "e": 1 if r.eoi else 0, "u": r.url,
                      "l": r.location[:60]})
    items.sort(key=lambda d: (d["e"], d["o"], d["t"]))
    fns = sorted({d["f"] for d in items})
    orgs = sorted({d["o"] for d in items})
    n_vac = sum(1 for d in items if not d["e"])
    n_open = sum(1 for d in items if not d["e"] and d["b"] == OPEN)
    opt = lambda vals: "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in vals)

    body = f"""
<h1>Open roles</h1>
<p class="lede">Every vacancy posted by the {len(orgs)} AI safety organizations in the newest snapshot
({human_date(latest_date)}). {n_open} of {n_vac} look open to early-career applicants.</p>
<p class="meta">Each role is read by the published rules, or by hand where it was part of an audited
snapshot (marked ✓). Links go to the organization's own posting. Roles close quickly, so check the date.</p>
<div class="filters">
  <input type="search" id="q" placeholder="Search titles and organizations" aria-label="Search">
  <select id="fn" aria-label="Kind of work"><option value="">All kinds of work</option>{opt(fns)}</select>
  <select id="org" aria-label="Organization"><option value="">All organizations</option>{opt(orgs)}</select>
  <label><input type="checkbox" id="op"> Open to early-career only</label>
  <label><input type="checkbox" id="eoi"> Include standing applications</label>
</div>
<p id="count"></p>
<div class="tw"><table class="roles"><thead><tr><th>Organization</th><th>Role</th><th>Kind of work</th><th>Level</th></tr></thead>
<tbody id="rows"></tbody></table></div>
"""
    js = """<script>
(function(){
var D=%s, L={open:'Open to early-career',unclear:"Doesn't say",closed:'Needs more experience'};
var q=document.getElementById('q'),fn=document.getElementById('fn'),org=document.getElementById('org'),
    op=document.getElementById('op'),eoi=document.getElementById('eoi'),tb=document.getElementById('rows'),
    ct=document.getElementById('count');
function e(s){return s.replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
try{var p=new URLSearchParams(location.search);if(p.get('open'))op.checked=true;}catch(_){}
function draw(){var s=q.value.trim().toLowerCase(),h='',n=0;
  D.forEach(function(d){
    if(d.e&&!eoi.checked)return; if(op.checked&&d.b!=='open')return;
    if(fn.value&&d.f!==fn.value)return; if(org.value&&d.o!==org.value)return;
    if(s&&(d.t+' '+d.o).toLowerCase().indexOf(s)<0)return; n++;
    var lvl=d.e?'<span class="tag">Standing application</span>':
      '<span class="tag'+(d.b==='open'?' o':'')+'">'+L[d.b]+'</span>'+(d.h?' <span class="small" title="Checked by hand">✓</span>':'');
    h+='<tr><td>'+e(d.o)+'</td><td><a href="'+e(d.u)+'" rel="noopener">'+e(d.t)+'</a>'+
      (d.l?'<div class="small">'+e(d.l)+'</div>':'')+'</td><td>'+e(d.f)+'</td><td>'+lvl+'</td></tr>';});
  tb.innerHTML=h||'<tr><td colspan="4" class="small">No roles match.</td></tr>';
  ct.textContent=n+(n===1?' role':' roles');}
[q,fn,org,op,eoi].forEach(function(x){x.addEventListener('input',draw);});draw();
})();
</script>""" % json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    write("roles.html", page("Open roles · AI Safety Hiring Snapshot",
                             "Every current vacancy at the AI safety organizations tracked, filterable.",
                             body, "roles.html", js))


def trends_page(snaps):
    """Like-for-like series: a fixed panel of orgs, measured on titles only."""
    frames = [(snap_date(p), load(p)) for p in snaps]
    api_sets = [set(f[(f.collection_method == "api") & f.native].org) for _, f in frames]
    panel = sorted(set.intersection(*api_sets))
    rows = []
    for d, f in frames:
        g = f[f.org.isin(panel) & ~f.eoi]
        m = len(g)
        rows.append(dict(date=d, n=m, entry=pct((g.level == "entry").sum(), m),
                         senior=pct((g.level == "senior").sum(), m),
                         all_orgs=f[f.native].org.nunique(), all_n=int((f.native & ~f.eoi).sum())))
    dates = [r["date"] for r in rows]
    nmax = max(r["n"] for r in rows)
    ymax_n = ((nmax // 20) + 1) * 20
    first, last = rows[0], rows[-1]
    growth = pct(last["n"] - first["n"], first["n"])
    smax = max(max(r["senior"] for r in rows), max(r["entry"] for r in rows))
    ymax_s = min(100, ((int(smax) // 10) + 1) * 10)

    c1 = line_chart(dates, [("Vacancies", [r["n"] for r in rows], "--open")],
                    ymax_n, lambda v: f"{v:.0f}", "Vacancies at the panel organizations")
    c2 = line_chart(dates, [("Senior title", [r["senior"] for r in rows], "--closed"),
                            ("Entry title", [r["entry"] for r in rows], "--open")],
                    ymax_s, lambda v: f"{v:.0f}%", "Share of vacancies by title seniority")
    table = data_table(["Snapshot", "Panel vacancies", "Entry title", "Senior title",
                        "All orgs tracked", "All vacancies"],
                       [(r["date"], r["n"], fmt_pct(r["entry"]), fmt_pct(r["senior"]),
                         r["all_orgs"], r["all_n"]) for r in rows], "Show every snapshot")

    body = f"""
<h1>Trends</h1>
<p class="lede">A fresh snapshot is collected every Monday and kept. {len(rows)} so far, from
{human_date(first['date'])} to {human_date(last['date'])}.</p>
<p>The organization list has grown over time, so totals across all snapshots are not comparable. These
charts follow a fixed panel instead: the {len(panel)} organizations read from a hiring feed in every snapshot
({esc(", ".join(panel))}).</p>

<div class="fig">
<h3>Vacancies at the panel organizations</h3>
<p class="sub">Concrete vacancies, standing applications excluded.</p>
{c1}
</div>
<p>Posted vacancies at these organizations went from {first['n']} to {last['n']} over the period, a change of
{growth:+.0f}%. That is a count of openings on the boards, not of hires.</p>

<div class="fig">
<h3>Title seniority over time</h3>
<p class="sub">Share of the panel's vacancies whose title carries a senior or an entry marker.</p>
{legend_line([("Senior title", "--closed"), ("Entry title", "--open")])}
{c2}
{table}
</div>
<p>Senior-titled roles went from {fmt_pct(first['senior'])} to {fmt_pct(last['senior'])} of the panel's
vacancies, and entry-titled roles from {fmt_pct(first['entry'])} to {fmt_pct(last['entry'])}. Title markers
understate how many roles are open to early-career applicants (see the <a href="index.html">findings</a>),
but because they are measured the same way every week, the direction is meaningful:
{"the boards have tilted toward senior hiring" if last['senior'] - first['senior'] >= 5 else "the seniority mix has held roughly steady" if abs(last['senior'] - first['senior']) < 5 else "the boards have tilted away from senior hiring"}.</p>

<div class="note"><b>Why titles only, here.</b> The headline measure reads the whole posting, but the
early snapshots cannot support it. Until 30 September 2026 the collector stored only the opening
paragraph of postings from Lever boards (METR, Epoch AI, Apollo Research), so their requirements are
missing from the archive. Title markers are unaffected, so they are the one measure that means the same
thing in every snapshot. All snapshots are re-scored with the current rules each time the site is built.</div>
<div class="note"><b>Organizations once read by hand are left out.</b> Until 30 September 2026 four
organizations without a hiring feed were captured by hand, and their rows were carried forward unchanged
between captures. They are no longer tracked, and the panel never included them.</div>
"""
    write("trends.html", page("Trends · AI Safety Hiring Snapshot",
                              "Weekly AI safety hiring snapshots, compared like for like.", body, "trends.html"))


def legend_line(items):
    return ('<div class="legend">' + "".join(
        f'<span class="lg"><i class="sw" style="background:var({v});height:3px;border-radius:2px"></i>{esc(n)}</span>'
        for n, v in items) + "</div>")


def method_page(a, a_all, audit_date, audit_path, latest, latest_date, ctx):
    n = len(a)
    xt = pd.crosstab(a.hand_label, a.rule_band).reindex(index=BANDS, columns=BANDS, fill_value=0)
    agree = int(sum(xt.loc[b, b] for b in BANDS))
    tp = int(xt.loc[OPEN, OPEN])
    rule_open = int(xt[OPEN].sum())
    hand_open = int(xt.loc[OPEN].sum())
    xt_rows = "".join(
        f"<tr><td>{BAND_LABEL[h]}</td>" + "".join(
            f'<td class="n">{"<b>" if h == r else ""}{int(xt.loc[h, r])}{"</b>" if h == r else ""}</td>'
            for r in BANDS) + f'<td class="n">{int(xt.loc[h].sum())}</td></tr>' for h in BANDS)
    dis = a[(a.hand_label == OPEN) != (a.rule_band == OPEN)]
    dis_rows = "".join(
        f"<tr><td>{esc(r.org)}</td><td>{esc(r.title)}</td><td>{BAND_LABEL[r.hand_label]}</td>"
        f"<td>{BAND_LABEL[r.rule_band]}</td><td class='small'>{esc(r.evidence)}</td></tr>"
        for r in dis.sort_values(["org", "title"]).itertuples())

    with_years = int(a.years.notna().sum())
    entry_markers = ", ".join(m for m in classify.ENTRY_MARKERS if m not in ("jr", "interns"))
    senior_markers = ", ".join(m for m in classify.SENIOR_MARKERS if m not in ("sr", "staff+", "vp"))

    body = f"""
<h1>Method and limits</h1>
<p class="lede">How the data is collected and classified, how the rules were checked by hand, and what
changed when the method was corrected.</p>

<h2>The question</h2>
<p>What share of the jobs AI safety organizations are advertising right now could someone early in their
career realistically apply for? "Early in their career" means two years of relevant full-time experience or
less: a strong new graduate, or someone moving over from another field.</p>

<h2>Where the data comes from</h2>
<p>Roles are read straight from each organization's own hiring system rather than from a curated job
board, which avoids the selection built into those boards. Every organization included publishes a
machine-readable feed through Greenhouse, Lever or Ashby, so the whole collection runs unattended each week.
The {human_date(audit_date)} snapshot holds {n} concrete vacancies.</p>
<p>Organizations with no feed are left out rather than read by hand. Hand capture was tried for four of them
(GovAI, Apart Research, Redwood Research, Palisade Research) and dropped: the rows went stale between
captures, and leaving those organizations out moves the headline share by less than one percentage point.
Every collection is also compared with the one before for organizations that fall to zero,
because a hiring feed that has been switched off looks exactly like an organization that stopped hiring.
That check caught the Center for AI Safety's move from Lever to Greenhouse in July 2026.</p>
<p>Standing "expression of interest" and "talent community" listings are kept in the data but left out of
every vacancy count.</p>

<h2>Which organizations count</h2>
<p>An organization is in if AI safety, security or governance is its main purpose and it has a hiring
system we can read. That includes nonprofits, one government body (the UK AI Security Institute) and four
safety-focused companies (Apollo Research, Goodfire, Haize Labs, Irregular). The companies sell products and
hire sales and marketing staff accordingly, so the findings page shows every figure with and without them.
Anthropic is tracked as a frontier-lab comparison and never mixed in. The <a href="coverage.html">coverage
page</a> lists every organization considered, including the ones left out and why.</p>

<h2>How roles are classified</h2>
<p>Three published rules, all in <code>classify.py</code>, with a regression test for each fix in
<code>test_classify.py</code>:</p>
<ul>
<li><b>Title markers.</b> Whole-word markers sort titles into <i>entry</i> ({esc(entry_markers)}, "associate",
and fellowship programs), <i>senior</i> ({esc(senior_markers)}), or <i>unspecified</i>. A title that names two
rungs ("Researcher / Senior Researcher") is not treated as senior-only. "Member of Technical Staff" is exempt
from "staff", and a bare "Manager" in a function title ("Product Manager", "Office Manager") is not read as a
rung.</li>
<li><b>Open-door statements.</b> A short list of plain phrases in the posting body that invite below-senior
applicants: "open to hires at junior…", "at all experience levels", "we don't require a formal background",
"an offer at the Associate level first". Phrases that describe juniors the new hire would manage are
deliberately excluded.</li>
<li><b>Stated experience floor.</b> The largest "N years" requirement in the posting, since listed
requirements are normally all required at once. The parser skips non-experience uses of "years" (visa
residency, post-employment bans, contract lengths). {with_years} of the {n} vacancies state a number.</li>
</ul>
<p>A role reads as <b>open</b> if its title carries an entry marker, or (with no senior marker) its text
states an open door or a floor of two years or less. It reads as <b>needs more experience</b> if the title is
senior or the floor is above two years, and as <b>doesn't say</b> otherwise. Kind of work (research,
engineering, operations and so on) comes from title keywords, with the hiring system's department as a
fallback.</p>

<h2 id="audit">Checking the rules by hand</h2>
<p>Rules miss things, so every one of the {n} vacancies in the {human_date(audit_date)} snapshot was also read
in full and labelled by hand, with the line that decided each label recorded next to it
(<a href="data/{os.path.basename(audit_path)}">download the labels</a>). The labels mean:</p>
<ul>
<li><b>Open to early-career</b>: the posting's own text makes it reachable with two years' experience or less.</li>
<li><b>Needs more experience</b>: a floor above two years, a senior or leadership scope, or a required PhD or
publication record. A conditional exception ("earlier-career applicants with a standout record may apply")
does not make a role open.</li>
<li><b>Doesn't say</b>: the posting gives no usable signal.</li>
</ul>
<p>The findings page reports these hand labels. The rules are what keep the weekly figures and the
<a href="roles.html">role list</a> up to date between audits, so it matters how well they match:</p>
<div class="tw"><table><thead><tr><th>Hand label ↓ · Rules →</th><th class="n">Open</th><th class="n">Doesn't say</th>
<th class="n">Needs more</th><th class="n">Total</th></tr></thead><tbody>{xt_rows}</tbody></table></div>
<p>The rules agree with the hand labels on {agree} of {n} vacancies. Of the {rule_open} they call open,
{tp} are open by hand; of the {hand_open} open by hand, they find {tp}. Two caveats. The open-door phrases were
written after reading this snapshot, so this agreement is partly by construction, and the real test is the next
audit. And the audit caught mistakes in both directions: one hand label was corrected after the rules found a
requirement the first reading missed.</p>
<p>The rules' main weakness is on the other side. {int(xt.loc[CLOSED, UNCLEAR])} roles they cannot place are,
on reading, clearly closed: a required PhD, "several years" written in words, a leadership scope described
rather than titled. So the rules overstate "doesn't say" and understate "needs more experience", while
their count of open roles stays close. For comparison, titles alone flag {fmt_pct(ctx['p_title'])} of
vacancies as open, about {word(round(ctx['p_open'] / ctx['p_title'])) if ctx['p_title'] else "none"} times fewer than the
hand-checked {fmt_pct(ctx['p_open'])}.</p>
<details class="dt"><summary>Where the rules and the hand labels disagree on "open"</summary>
<div class="tw"><table><thead><tr><th>Organization</th><th>Role</th><th>Hand</th><th>Rules</th><th>Why</th></tr></thead>
<tbody>{dis_rows}</tbody></table></div></details>

<h2>What to keep in mind</h2>
<ul>
<li><b>Postings are not need.</b> Senior and network hiring often goes unadvertised, so this undercounts senior
demand and should not be read as where the field most needs people.</li>
<li><b>Fellowships are the main way in, and mostly invisible here.</b> MATS, SPAR, GovAI's seasonal fellowships
and similar programs recruit on their own cycles. A field-wide picture of entry routes would need to count them.</li>
<li><b>Small numbers.</b> {n} vacancies is the whole population for these organizations, not a sample, but
per-organization and per-function figures rest on a handful of roles and move a lot week to week.</li>
<li><b>One reader.</b> The hand labels are one careful reading. Where you disagree, the evidence column
shows exactly what the label rests on.</li>
</ul>

<h2>Corrections</h2>
<p>This project publishes its mistakes. Every figure on the site is re-computed from the raw snapshots with the
current rules, so older figures quoted elsewhere may differ.</p>
<ul>
<li><b>30 September 2026, method overhaul.</b>
<ul>
<li>Hand audit added. The old headline put the open share at about 5%, counting title keywords. Reading
every posting gives {fmt_pct(ctx['p_open'])}, because most open roles say so in the body rather than the
title.</li>
<li>Markers now match whole words. Substring matching had read "International" as "intern", so
"Director, US International Tax" counted as an early-career role in the Anthropic comparison.</li>
<li>The experience floor now takes the largest stated requirement, not the smallest. "10+ years… 2+ years of
people management" had read as a two-year floor.</li>
<li>Lever postings are now stored in full. Before, only the opening paragraph was kept, leaving requirements
unreadable for METR, Epoch AI, Apollo Research and FAR.AI.</li>
<li>Hand capture dropped. Rows for the four organizations without a hiring feed were carried forward
between captures, and closed GovAI roles, including the Research Scholar position the old headline counted as
a way in, had stayed in the count for two months. Those organizations are now left out; with them, the
hand-checked open share was 18.3%, without them {fmt_pct(ctx['p_open'])}.</li>
<li>Seven organizations added (FAR.AI, LawZero, Kairos, AVERI, CAIS Action Fund, Haize Labs, Irregular),
and each organization is now typed as nonprofit, government or company.</li>
<li>Two-rung titles, bare "Manager" titles and "Associate" titles are handled as described above.</li>
</ul></li>
<li><b>26 July 2026.</b> The Center for AI Safety's move from Lever to Greenhouse was caught and fixed; "Fellow"
was split into program fellowships (entry) and think-tank Research Fellow roles (not entry).</li>
</ul>
"""
    write("methodology.html", page("Method · AI Safety Hiring Snapshot",
                                   "How the AI safety hiring data is collected, classified and checked.",
                                   body, "methodology.html"))


def coverage_page(latest, latest_date):
    counts = latest.org.value_counts()
    vac = latest[~latest.eoi].org.value_counts()
    grouped = {}
    for o in ORGS:
        g = grouped.setdefault(o["name"], dict(o, sources=[]))
        g["sources"].append(o["source"])
    rows = ""
    for name, o in grouped.items():
        if o["category"] == "frontier-lab":
            status = '<span class="tag">comparison only</span>'
        else:
            status = '<span class="tag o">hiring feed</span>'
        fresh = latest_date
        in_snap = int(counts.get(name, 0))
        rows += (f"<tr><td>{esc(name)}</td><td>{esc(o['org_type'])}</td>"
                 f"<td>{esc(' + '.join(sorted(set(o['sources']))))}</td><td>{status}</td>"
                 f"<td class='n'>{int(vac.get(name, 0))}</td><td class='n'>{in_snap}</td>"
                 f"<td>{esc(fresh)}</td></tr>")
    ex_rows = ""
    xpath = os.path.join(HERE, "orgs_excluded.csv")
    if os.path.exists(xpath):
        with open(xpath, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ex_rows += f"<tr><td>{esc(r['name'])}</td><td>{esc(r['reason'])}</td><td>{esc(r['checked'])}</td></tr>"
    n_in = sum(1 for o in grouped.values() if o["category"] != "frontier-lab")
    body = f"""
<h1>Coverage</h1>
<p class="lede">Every organization considered, where its hiring data comes from, and whether it is counted.
The point of this page is that you can see exactly what is and is not in the numbers.</p>
<h2>Included ({n_in}, plus one comparison)</h2>
<p class="meta">Figures from the newest snapshot, {human_date(latest_date)}. Listings include standing
applications; vacancies do not. "As of" is the date the data was last read.</p>
<div class="tw"><table><thead><tr><th>Organization</th><th>Type</th><th>Source</th><th>Status</th>
<th class="n">Vacancies</th><th class="n">Listings</th><th>As of</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Considered and left out</h2>
<p>Checked for a readable public hiring feed on the date shown. Several are central to the field; their
absence is the main limit on coverage.</p>
<div class="tw"><table><thead><tr><th>Organization</th><th>Why it is not included</th><th>Checked</th></tr></thead>
<tbody>{ex_rows}</tbody></table></div>
<p>Raw data: <a href="data/snapshot_{latest_date}.csv">snapshot_{latest_date}.csv</a> · every snapshot is in
<a href="{REPO_URL}/tree/main/data/snapshots">the repository</a>.</p>
"""
    write("coverage.html", page("Coverage · AI Safety Hiring Snapshot",
                                "Every organization considered for the AI safety hiring snapshot.",
                                body, "coverage.html"))


if __name__ == "__main__":
    os.makedirs(SITE, exist_ok=True)
    build()
