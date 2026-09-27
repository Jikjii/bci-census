"""Render the static site in docs/ (served by GitHub Pages)."""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from .tally import registry_count
from .util import date_key

TIER_TEXT = {"A": "Registry or paper", "B": "Company statement", "C": "Press report", "D": "Aggregator"}
QUALIFIER = {"at_least": "at least ", "about": "about ", "exact": ""}
BASIS_TEXT = {
    "sourced": "Sourced count",
    "registry": "ClinicalTrials.gov actual enrollment",
    "none": "No sourced count yet",
}
KIND_TEXT = {
    "new_trial": "New trial",
    "status_change": "Trial status",
    "enrollment_change": "Trial enrollment",
    "trial_dropped": "Removed from scope",
    "fda_decision": "FDA decision",
    "form_d": "SEC Form D",
    "fact_counts": "New sourced count",
    "fact_regulatory": "New approval or designation",
    "fact_funding": "New funding",
    "first_pull": "First live pull",
    "floor_change": "Verified floor",
}


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def pretty_date(value: str) -> str:
    s = str(value or "")
    try:
        d = dt.date.fromisoformat(s)
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    except ValueError:
        pass
    try:
        d = dt.datetime.strptime(s, "%Y-%m")
        return d.strftime("%b %Y")
    except ValueError:
        return s


def link(url: str, text: str) -> str:
    if not url:
        return esc(text)
    return f'<a href="{esc(url)}" rel="noopener">{esc(text)}</a>'


def tier_badge(tier: str) -> str:
    if not tier:
        return ""
    return f'<span class="tier" title="{esc(TIER_TEXT.get(tier, ""))}">Tier {esc(tier)}</span>'


def money(amount) -> str:
    if not isinstance(amount, (int, float)) or not amount:
        return "—"
    if amount >= 1e9:
        return f"${amount / 1e9:,.2f}B"
    return f"${amount / 1e6:,.1f}M"


CSS = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10); --bar: #2a78d6; --wash: rgba(42,120,214,0.10);
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --bar: #3987e5; --wash: rgba(57,135,229,0.14);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --bar: #3987e5; --wash: rgba(57,135,229,0.14);
}
* { box-sizing: border-box; }
html { background: var(--page); }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
a { color: var(--ink); text-decoration-color: var(--axis); text-underline-offset: 2px; }
a:hover { text-decoration-color: var(--ink); }
.wrap { max-width: 1040px; margin: 0 auto; padding: 0 16px 64px; }
header.top { display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: baseline; justify-content: space-between; padding: 24px 0 8px; }
.brand { font-weight: 600; font-size: 18px; letter-spacing: -0.01em; }
nav { display: flex; flex-wrap: wrap; gap: 4px 16px; }
nav a { color: var(--ink-2); text-decoration: none; font-size: 14px; white-space: nowrap; }
nav a:hover { color: var(--ink); }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin: 16px 0; }
h1 { font-size: 20px; font-weight: 600; margin: 0 0 4px; }
h2 { font-size: 18px; font-weight: 600; margin: 0 0 4px; }
.sub { color: var(--ink-2); margin: 0 0 16px; font-size: 15px; }
.hero { display: grid; grid-template-columns: auto 1fr; gap: 8px 24px; align-items: center; }
.hero .figure { font-size: 72px; line-height: 1; font-weight: 600; letter-spacing: -0.03em; }
.hero p { margin: 0; color: var(--ink-2); max-width: 560px; }
.hero p strong { color: var(--ink); font-weight: 600; }
.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-top: 24px; }
.kpi { border-top: 1px solid var(--grid); padding-top: 12px; }
.kpi .label { color: var(--ink-2); font-size: 14px; }
.kpi .value { font-size: 28px; font-weight: 600; letter-spacing: -0.01em; }
.chart { position: relative; margin-top: 8px; }
.row { display: grid; grid-template-columns: 190px 1fr; gap: 12px; align-items: center; padding: 6px 0; border-radius: 6px; outline: none; }
.row:hover .bar, .row:focus-visible .bar { opacity: 0.8; }
.row:focus-visible { box-shadow: 0 0 0 2px var(--axis); }
.row .name { font-size: 14px; color: var(--ink); text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.track { display: flex; align-items: center; gap: 8px; border-left: 1px solid var(--axis); min-height: 24px; }
.bar { height: 20px; background: var(--bar); border-radius: 0 4px 4px 0; min-width: 2px; }
.val { font-size: 14px; color: var(--ink-2); font-variant-numeric: tabular-nums; white-space: nowrap; }
.tip { position: absolute; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: 13px; box-shadow: 0 4px 16px rgba(0,0,0,0.12); max-width: 280px; display: none; z-index: 2; }
.tip b { display: block; font-size: 16px; font-weight: 600; }
.tip span { display: block; color: var(--ink-2); }
.tablewrap { overflow-x: auto; margin: 0 -4px; }
table { width: 100%; min-width: 640px; border-collapse: collapse; font-size: 14px; }
th { text-align: left; font-weight: 600; color: var(--ink-2); border-bottom: 1px solid var(--axis); padding: 8px 6px; white-space: nowrap; }
td { border-bottom: 1px solid var(--grid); padding: 8px 6px; vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.small { font-size: 13px; color: var(--ink-2); }
.nowrap { white-space: nowrap; }
.tier { display: inline-block; font-size: 12px; color: var(--ink-2); border: 1px solid var(--border); border-radius: 999px; padding: 0 7px; margin-left: 4px; white-space: nowrap; }
ul.changes { margin: 0; padding-left: 18px; }
ul.changes li { margin: 6px 0; }
.empty { color: var(--ink-2); font-style: italic; }
footer { color: var(--ink-2); font-size: 14px; padding-top: 24px; }
@media (max-width: 720px) {
  .hero { grid-template-columns: 1fr; }
  .hero .figure { font-size: 60px; }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .row { grid-template-columns: 120px 1fr; }
  table.stack { min-width: 0; }
  table.stack thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  table.stack, table.stack tbody, table.stack tr, table.stack td { display: block; }
  table.stack tr { border-bottom: 1px solid var(--grid); padding: 10px 0; }
  table.stack td { border: 0; padding: 2px 0; text-align: left; white-space: normal; }
  table.stack td[data-label] { position: relative; padding-left: 112px; }
  table.stack td[data-label]::before { content: attr(data-label); position: absolute; left: 0; width: 100px;
    color: var(--ink-2); font-size: 12px; font-weight: 600; line-height: 1.9; }
  table.stack .hide-sm, table.stack td[data-label]:empty { display: none; }
}
"""

JS = """
(function () {
  var chart = document.getElementById('floor-chart');
  if (!chart) return;
  var tip = chart.querySelector('.tip');
  function show(row, x, y) {
    var d = JSON.parse(row.getAttribute('data-tip'));
    tip.textContent = '';
    var b = document.createElement('b'); b.textContent = d.value; tip.appendChild(b);
    [d.name, d.basis, d.source].forEach(function (t) {
      if (!t) return; var s = document.createElement('span'); s.textContent = t; tip.appendChild(s);
    });
    tip.style.display = 'block';
    var box = chart.getBoundingClientRect();
    var left = Math.min(x - box.left + 12, box.width - tip.offsetWidth);
    tip.style.left = Math.max(0, left) + 'px';
    tip.style.top = (y - box.top + 12) + 'px';
  }
  function hide() { tip.style.display = 'none'; }
  chart.querySelectorAll('.row').forEach(function (row) {
    row.addEventListener('pointermove', function (e) { show(row, e.clientX, e.clientY); });
    row.addEventListener('pointerleave', hide);
    row.addEventListener('focus', function () {
      var r = row.getBoundingClientRect(); show(row, r.left + r.width / 2, r.top + r.height / 2);
    });
    row.addEventListener('blur', hide);
  });
})();
"""


def _floor_cell(row: dict) -> str:
    if row["floor"] == 0:
        return '<td class="num" data-label="Verified floor">—</td><td class="small" data-label="Basis">No sourced count yet</td>'
    if row["basis"] == "sourced":
        fact = row["sourced_fact"]
        detail = (
            f"{esc(QUALIFIER.get(fact.get('qualifier', ''), ''))}{row['floor']:,} as of {esc(pretty_date(fact['as_of']))} · "
            f"{link(fact['source_url'], fact.get('source_title') or 'source')}{tier_badge(fact['tier'])}"
        )
    else:
        parts = [
            f'{link("https://clinicaltrials.gov/study/" + d["nct_id"], d["nct_id"])}: {d["count"]:,}'
            + (" implanted, per paper" if d.get("sourced") else "")
            for d in row.get("registry_detail") or [{"nct_id": n, "count": 0} for n in row["registry_trials"]]
        ]
        detail = "ClinicalTrials.gov, " + ", ".join(parts) + tier_badge("A")
    return f'<td class="num" data-label="Verified floor">{row["floor"]:,}</td><td class="small" data-label="Basis">{detail}</td>'


def _chart(rows: list[dict]) -> str:
    counted = [r for r in rows if r["floor"] > 0]
    if not counted:
        return '<p class="empty">No program has a sourced count yet.</p>'
    top = max(r["floor"] for r in counted)
    parts = ['<div class="chart" id="floor-chart" role="img" aria-label="Verified floor by program">']
    for r in counted:
        width = max(1.0, 100.0 * r["floor"] / top)
        fact = r.get("sourced_fact") or {}
        tip = {
            "value": f"{r['floor']:,} people",
            "name": r["name"],
            "basis": BASIS_TEXT.get(r["basis"], ""),
            "source": f"Tier {fact.get('tier')}, as of {pretty_date(fact.get('as_of', ''))}" if fact else "Tier A, registry",
        }
        parts.append(
            f'<div class="row" tabindex="0" data-tip="{esc(json.dumps(tip))}">'
            f'<div class="name">{esc(r["name"])}</div>'
            f'<div class="track"><div class="bar" style="width: calc({width:.2f}% - 48px)"></div>'
            f'<span class="val">{r["floor"]:,}</span></div></div>'
        )
    parts.append('<div class="tip" role="tooltip"></div></div>')
    return "".join(parts)


def _programs_table(rows: list[dict], latest_event: dict) -> str:
    body = []
    for r in rows:
        if r["program"] == "academic-other" and r["floor"] == 0 and r["trials_in_scope"] == 0:
            continue
        event = latest_event.get(r["program"])
        event_html = f'{esc(event["event"])} <span class="small">({esc(pretty_date(event["date"]))})</span>' if event else "—"
        body.append(
            "<tr>"
            f'<td class="lead"><strong>{esc(r["name"])}</strong><div class="small">{esc(r["device"])}</div></td>'
            f'<td class="small hide-sm" data-label="Approach">{esc(r["approach"])}</td>'
            f'<td class="small" data-label="Country">{esc(r["hq_country"])}</td>'
            f"{_floor_cell(r)}"
            f'<td class="num" data-label="Trials">{r["trials_in_scope"]}</td>'
            f'<td data-label="Latest event">{event_html}</td>'
            "</tr>"
        )
    head = (
        "<tr><th>Program</th><th class=\"hide-sm\">Approach</th><th>Country</th><th class=\"num\">Verified floor</th>"
        "<th>Basis</th><th class=\"num\">Trials</th><th>Latest event</th></tr>"
    )
    return f'<div class="tablewrap"><table class="programs stack"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def _trials_table(trials: list[dict], names: dict, order: dict | None = None, as_of: str = "") -> str:
    if not trials:
        return (
            '<p class="empty">Trials appear after the first live pull from ClinicalTrials.gov, '
            "which runs on GitHub every Monday.</p>"
        )
    rows = []
    order = order or {}
    newest_first = sorted(trials, key=lambda t: date_key(t.get("start_date", "")), reverse=True)
    for t in sorted(newest_first, key=lambda t: order.get(t.get("program", ""), len(order))):  # programs in floor order
        enroll = t.get("enrollment")
        etype = (t.get("enrollment_type") or "").lower()
        enroll_txt = esc(f"{enroll:,} ({etype})") if isinstance(enroll, int) else "—"
        counted = registry_count(t, as_of) if as_of else 0
        if t.get("implanted") is not None:  # a paper or the sponsor gives the number actually implanted
            implanted = "{:,} implanted per source".format(t["implanted"])
            enroll_txt += f'<div class="small">{link(t.get("implanted_source", ""), implanted)}{"; in the floor" if counted else ""}</div>'
        elif counted:
            enroll_txt += '<div class="small">in the floor</div>'
        rows.append(
            "<tr>"
            f'<td class="lead">{link(t.get("url", ""), t.get("nct_id", ""))}</td>'
            f'<td class="lead">{esc(t.get("title", ""))}<div class="small">{esc(t.get("sponsor", ""))}</div></td>'
            f'<td class="small" data-label="Program">{esc(names.get(t.get("program", ""), t.get("program", "")))}</td>'
            f'<td class="small" data-label="Status">{esc((t.get("status") or "").replace("_", " ").lower())}</td>'
            f'<td class="num" data-label="Enrollment">{enroll_txt}</td>'
            f'<td class="small" data-label="Implant">{esc(t.get("duration", ""))}</td>'
            f'<td class="small nowrap" data-label="Start">{esc(pretty_date(t.get("start_date", "")))}</td>'
            f'<td class="small" data-label="Countries">{esc(", ".join(t.get("countries") or []))}</td>'
            "</tr>"
        )
    head = (
        "<tr><th>Trial</th><th>Title and sponsor</th><th>Program</th><th>Status</th>"
        '<th class="num">Enrollment</th><th>Implant</th><th>Start</th><th>Countries</th></tr>'
    )
    return f'<div class="tablewrap"><table class="stack"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'


def _events_table(regulatory: list[dict], fda: list[dict], names: dict) -> str:
    items = [
        {"date": e["date"], "who": names.get(e["program"], e["program"].title()), "what": e["event"], "url": e["source_url"], "tier": e["tier"]}
        for e in regulatory
    ]
    covered = {e.get("fda_id") for e in regulatory if e.get("fda_id")}
    for d in fda:
        if d.get("program") and d.get("id") not in covered:
            items.append(
                {
                    "date": d.get("decision_date", ""),
                    "who": names.get(d["program"], d["program"]),
                    "what": f'{d["kind"]} {d["id"]}: {d.get("device_name", "")} ({d.get("decision", "")})',
                    "url": d.get("url", ""),
                    "tier": "A",
                }
            )
    items.sort(key=lambda i: date_key(i["date"]), reverse=True)
    rows = "".join(
        f'<tr><td class="small" data-label="Date">{esc(pretty_date(i["date"]))}</td><td data-label="Who">{esc(i["who"])}</td>'
        f'<td data-label="Event">{link(i["url"], i["what"])}{tier_badge(i["tier"])}</td></tr>'
        for i in items
    )
    return (
        '<div class="tablewrap"><table class="stack"><thead><tr><th>Date</th><th>Who</th><th>Event</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def _funding_table(funding: list[dict], form_d: list[dict], names: dict) -> str:
    items = [
        {"date": f["date"], "who": names.get(f["program"], f["program"]), "what": f["event"], "amount": f.get("amount_usd"), "url": f["source_url"], "tier": f["tier"]}
        for f in funding
    ]
    for f in form_d:
        investors = f.get("investors_count")
        extra = f", {investors} investors" if investors else ""
        items.append(
            {
                "date": f.get("filing_date", ""),
                "who": names.get(f.get("program", ""), f.get("company", "")),
                "what": f'Form {f.get("form", "D")} filed; first sale {pretty_date(f.get("date_of_first_sale", "")) or "not stated"}{extra}',
                "amount": f.get("total_amount_sold"),
                "url": f.get("url", ""),
                "tier": "A",
            }
        )
    items.sort(key=lambda i: date_key(i["date"]), reverse=True)
    rows = "".join(
        f'<tr><td class="small" data-label="Date">{esc(pretty_date(i["date"]))}</td><td data-label="Who">{esc(i["who"])}</td>'
        f'<td class="num" data-label="Amount">{esc(money(i["amount"]))}</td><td data-label="Event">{link(i["url"], i["what"])}{tier_badge(i["tier"])}</td></tr>'
        for i in items
    )
    return (
        '<div class="tablewrap"><table class="stack"><thead><tr><th>Date</th><th>Who</th><th class="num">Amount</th><th>Event</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def _changes(changes: dict, names: dict) -> str:
    if changes.get("first_run"):
        return '<p class="empty">First edition. Next week this section lists every change since today.</p>'
    items = changes.get("items") or []
    if not items:
        return f'<p class="empty">Nothing changed in the registries since {esc(pretty_date(changes.get("since", "")))}.</p>'
    lis = "".join(
        f'<li><strong>{esc(KIND_TEXT.get(i["kind"], i["kind"]))}:</strong> {link(i.get("url", ""), i["title"])} '
        f'<span class="small">{esc(i.get("detail", ""))}</span></li>'
        for i in items
    )
    return f'<ul class="changes">{lis}</ul>'


def render(census: dict, trials: list[dict], fda: list[dict], form_d: list[dict], changes: dict, bundle: dict,
           site_url: str, repo_url: str, x_handle: str) -> str:
    names = {p["id"]: p["name"] for p in bundle["programs"]}
    names.update({"academic-other": "Academic and other", "ecosystem": "Ecosystem", "policy": "Policy"})
    latest_event: dict = {}
    for e in sorted(bundle["regulatory"], key=lambda e: date_key(e["date"])):
        latest_event[e["program"]] = e

    total = census["total_floor"]
    rng = census.get("other_range")
    range_txt = f"{rng[0]:,} to {rng[1]:,}" if rng else "widely"
    in_scope = [t for t in trials if t.get("in_scope")]
    active = sum(1 for t in in_scope if t.get("status") in ("RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING"))
    as_of = census["as_of"]
    desc = (
        f"At least {total} people are verified to be living with an implanted brain-computer interface. "
        "Every number has a source. Updated weekly."
    )
    other_rows = "".join(
        f'<tr><td class="lead">{link(o["source_url"], o["label"])}</td><td class="num" data-label="Count">{esc(QUALIFIER.get(o.get("qualifier", ""), ""))}{int(o["value"]):,}</td>'
        f'<td class="small" data-label="As of">{esc(pretty_date(o["as_of"]))}</td><td class="small" data-label="Note">{esc(o.get("note", ""))}</td></tr>'
        for o in census.get("other_counts") or []
    )
    queue_rows = "".join(
        f'<li><strong>{esc(names.get(q.get("program", ""), q.get("program", "")))}:</strong> {esc(q["claim"])}'
        f'<div class="small">{esc(q.get("lead", ""))}</div></li>'
        for q in census.get("verify_queue") or []
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BCI Census: people living with implanted brain-computer interfaces</title>
<meta name="description" content="{esc(desc)}">
<meta property="og:title" content="BCI Census">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(site_url)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="BCI Census">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:site" content="@{esc(x_handle)}">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="brand">BCI Census</div>
  <nav><a href="#programs">Programs</a><a href="#changes">This week</a><a href="#trials">Trials</a><a href="#events">Approvals</a><a href="#funding">Funding</a><a href="#method">Method</a></nav>
</header>

<section class="card">
  <div class="hero">
    <div class="figure">{total:,}</div>
    <p><strong>people are verified to be living with an implanted brain-computer interface</strong>, as of {esc(pretty_date(as_of))}.
    This is a floor: every person counted has a source, and the true number is likely higher.
    Other published counts run from {esc(range_txt)}; the <a href="#method">method</a> explains why.</p>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="label">Programs with a verified count</div><div class="value">{census["programs_counted"]}</div></div>
    <div class="kpi"><div class="label">Implanted BCI trials tracked</div><div class="value">{len(in_scope)}</div></div>
    <div class="kpi"><div class="label">Trials active or recruiting</div><div class="value">{active}</div></div>
    <div class="kpi"><div class="label">Claims waiting for a source</div><div class="value">{len(census.get("verify_queue") or [])}</div></div>
  </div>
</section>

<section class="card" id="programs">
  <h2>Verified floor by program</h2>
  <p class="sub">People with a chronic implant, from the most recent sourced count or ClinicalTrials.gov actual enrollment, whichever is larger. Hover or focus a bar for its source.</p>
  {_chart(census["programs"])}
  <div style="height:16px"></div>
  {_programs_table(census["programs"], latest_event)}
</section>

<section class="card" id="changes">
  <h2>What changed this week</h2>
  <p class="sub">Compared with the previous weekly snapshot.</p>
  {_changes(changes, names)}
</section>

<section class="card" id="trials">
  <h2>Implanted BCI trials</h2>
  <p class="sub">From ClinicalTrials.gov. Only actual enrollment counts toward the floor; estimated enrollment is a target. <a href="data/trials_all.csv">Every trial reviewed, with the reason it was kept or excluded</a>.</p>
  {_trials_table(in_scope, names, {r["program"]: i for i, r in enumerate(census["programs"])}, as_of)}
</section>

<section class="card" id="events">
  <h2>Approvals, designations and policy</h2>
  <p class="sub">Curated events plus FDA decisions pulled from openFDA.</p>
  {_events_table(bundle["regulatory"], fda, names)}
</section>

<section class="card" id="funding">
  <h2>Funding and SEC filings</h2>
  <p class="sub">Announced rounds plus Form D filings pulled from SEC EDGAR.</p>
  {_funding_table(bundle["funding"], form_d, names)}
</section>

<section class="card" id="method">
  <h2>Why counts disagree, and how this one works</h2>
  <p>Published counts mix three different numbers: people with permanent implants, people with temporary implants placed during surgery, and trial enrollment targets. They also include or leave out China, and rarely subtract devices that were removed. The census keeps these apart and counts only permanent implants with a source.</p>
  <p>Each program's floor is the larger of its latest sourced count and the actual enrollment of its permanent-implant trials that are still following participants or ended in the last five years. Older trials are listed but not counted, because their participants may have had devices removed. People are counted unless a source reports a removal or death.</p>
  <p>Each fact has a tier: <strong>A</strong> registry or peer-reviewed paper, <strong>B</strong> company statement, <strong>C</strong> credible press report. Aggregator figures (<strong>D</strong>) are shown below for context and never counted. Full rules: <a href="{esc(repo_url)}/blob/main/METHODOLOGY.md">METHODOLOGY.md</a>.</p>
  <h2 style="margin-top:20px">Other published counts</h2>
  <div class="tablewrap"><table class="stack"><thead><tr><th>Source</th><th class="num">Count</th><th>As of</th><th>Note</th></tr></thead><tbody>{other_rows}</tbody></table></div>
  <h2 style="margin-top:20px">Claims waiting for a source</h2>
  <p class="sub">Have one? <a href="{esc(repo_url)}/issues/new">Open an issue</a> with the link and it gets credited.</p>
  <ul class="changes">{queue_rows}</ul>
</section>

<footer>
  Data: <a href="data/census.json">census.json</a> · <a href="data/programs.csv">programs.csv</a> · <a href="data/trials.csv">trials.csv</a> · <a href="data/events.csv">events.csv</a> · <a href="data/funding.csv">funding.csv</a>.
  Code on <a href="{esc(repo_url)}">GitHub</a> (MIT); data CC BY 4.0. Weekly updates on X: <a href="https://x.com/{esc(x_handle)}">@{esc(x_handle)}</a>.
  Sources: ClinicalTrials.gov, openFDA and SEC EDGAR, which do not endorse this project. No personal data is collected or published. Not medical advice.
</footer>
</div>
<script>{JS}</script>
</body>
</html>
"""
