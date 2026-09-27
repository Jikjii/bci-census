"""Draft the weekly X thread. Every post is checked against X's 280-character limit."""

from __future__ import annotations

import datetime as dt
import re

URL_RE = re.compile(r"https?://\S+")

# X weights most Latin characters as 1 and others as 2; every URL counts as 23.
_LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))

EXPLAINERS = [
    "Why do published counts run from about 50 to about 250? Most mix three numbers: permanent implants, "
    "temporary implants placed during surgery, and trial enrollment targets. The census keeps them apart.",
    "Counts also split on China. Chinese programs now report dozens of implants and the first commercial "
    "approval, but many English-language tallies leave them out. The census includes them, with sources.",
    "A trial target is not an implant. A study listed for 30 people may have implanted 5 so far. "
    "The census counts actual enrollment only, never the target.",
    "Every number in the census has a tier: A for registries and papers, B for company statements, "
    "C for press reports. Aggregator claims are shown for context but never counted.",
    "Removals count too. When a source reports that a device came out, the census subtracts it. "
    "Most tallies never do, which is one more reason they drift upward.",
]

KIND_LABEL = {
    "new_trial": "New trial",
    "status_change": "Trial update",
    "enrollment_change": "Enrollment update",
    "trial_dropped": "Removed from scope",
    "fda_decision": "FDA",
    "form_d": "SEC Form D",
    "fact_counts": "New count",
    "fact_regulatory": "New approval or designation",
    "fact_funding": "New funding",
    "first_pull": "Added",
    "floor_change": "Floor",
}

MAX_LEN = 280


def x_length(text: str) -> int:
    stripped = URL_RE.sub("", text)
    length = 23 * len(URL_RE.findall(text))
    for ch in stripped:
        cp = ord(ch)
        length += 1 if any(lo <= cp <= hi for lo, hi in _LIGHT_RANGES) else 2
    return length


def _fit(text: str) -> str:
    """Trim a post to 280 weighted characters, cutting at a line break or word."""
    if x_length(text) <= MAX_LEN:
        return text
    lines = text.split("\n")
    while len(lines) > 1 and x_length("\n".join(lines)) > MAX_LEN:
        lines.pop()
    text = "\n".join(lines)
    while x_length(text + "…") > MAX_LEN and " " in text:
        text = text.rsplit(" ", 1)[0]
    return text if x_length(text) <= MAX_LEN else text[: MAX_LEN - 1] + "…"


def _pretty(iso: str) -> str:
    try:
        d = dt.date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _program_lines(census: dict, limit: int = 5) -> list[str]:
    lines = []
    for r in [r for r in census["programs"] if r["floor"] > 0][:limit]:
        country = r.get("hq_country") or ""
        tag = f" ({country})" if country and country != "United States" else ""
        lines.append(f"{r['name']}{tag}: {r['floor']}")
    return lines


def _launch_thread(census: dict, trials_tracked: int, site_url: str, repo_url: str, as_of: str) -> list[str]:
    total, counted = census["total_floor"], census["programs_counted"]
    tracked = f" ({trials_tracked} implanted BCI trials so far)" if trials_tracked else ""
    rng = census.get("other_range")
    spread = f"Published counts run from {rng[0]} to {rng[1]}." if rng else "Published counts disagree widely."
    posts = [
        f"How many people are living with a brain-computer interface implant? {spread}\n\n"
        f"So I built a census where every person counted has a source. As of {_pretty(as_of)}: at least {total}, "
        f"across {counted} programs.\n\n{site_url}",
        "Why the counts disagree: they mix permanent implants, temporary ones placed during surgery, and trial "
        "enrollment targets. Some leave out China. Few subtract devices that were removed. The census keeps these apart.",
    ]
    lines = _program_lines(census)
    if lines:
        posts.append("Verified floor by program:\n" + "\n".join(lines))
    posts += [
        "How a number gets in: registry records and papers (tier A), company statements (B) or credible press (C). "
        "Aggregator totals are shown but never counted. Trial targets never count, only actual enrollment.",
        f"Every Monday the census re-pulls ClinicalTrials.gov{tracked}, FDA decisions and SEC Form D filings, and "
        f"this account posts what changed. Code and data: {repo_url}",
        f"Found an error, or have a source I don't? Open an issue and it gets credited: {repo_url}/issues",
    ]
    return [_fit(p) for p in posts]


def build_thread(census: dict, changes: dict, site_url: str, repo_url: str, as_of: str, trials_tracked: int = 0) -> list[str]:
    if changes.get("first_run"):
        return _launch_thread(census, trials_tracked, site_url, repo_url, as_of)

    total = census["total_floor"]
    counted = census["programs_counted"]
    posts = [
        f"BCI Census, {_pretty(as_of)}: at least {total} people are living with an implanted brain-computer "
        f"interface, across {counted} programs. Every number links to its source.\n\n{site_url}"
    ]
    items = changes.get("items") or []
    before, after = changes.get("floor_before"), changes.get("floor_after")
    head = f"Verified floor: {before} → {after}." if before is not None and before != after else "Verified floor unchanged."
    if items:
        lines = [f"- {KIND_LABEL.get(i['kind'], i['kind'])}: {i['title']}" for i in items[:4]]
        more = len(items) - 4
        if more > 0:
            lines.append(f"- plus {more} more on the site")
        posts.append(f"What changed this week. {head}\n" + "\n".join(lines))
    else:
        posts.append(f"What changed this week: nothing in the registries. {head}")

    lines = _program_lines(census)
    if lines:
        posts.append("Verified floor by program:\n" + "\n".join(lines))

    week = dt.date.fromisoformat(as_of).isocalendar().week if re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of) else 0
    posts.append(EXPLAINERS[week % len(EXPLAINERS)])
    posts.append(f"Found an error, or have a source I don't? Open an issue and it gets credited: {repo_url}/issues")
    return [_fit(p) for p in posts]


def render_markdown(posts: list[str], as_of: str) -> str:
    out = [f"# X draft for {as_of}", "", "Post as a thread. Character counts use X's weighting (URLs = 23).", ""]
    for n, post in enumerate(posts, 1):
        out += [f"## {n}/{len(posts)} ({x_length(post)} chars)", "", post, ""]
    return "\n".join(out)
