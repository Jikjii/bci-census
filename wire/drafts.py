"""Draft posts. Every draft fits X's 280-character limit, carries no link (the link goes in
your reply, because X's ranking pushes down posts that send people away), and adds the
census context, which is what makes the post original reporting rather than aggregation.
"""

from __future__ import annotations

import datetime as dt
import urllib.parse

from census.post import _fit, x_length

from .items import Item

INTENT = "https://twitter.com/intent/tweet?text="

STATUS_TEXT = {
    "NOT_YET_RECRUITING": "not yet recruiting",
    "RECRUITING": "recruiting",
    "ENROLLING_BY_INVITATION": "enrolling by invitation",
    "ACTIVE_NOT_RECRUITING": "active, not recruiting",
    "COMPLETED": "completed",
    "TERMINATED": "terminated",
    "SUSPENDED": "suspended",
    "WITHDRAWN": "withdrawn",
}


def fit(text: str) -> str:
    return _fit(" ".join(text.split()))


def intent_url(text: str) -> str:
    return INTENT + urllib.parse.quote(text, safe="")


def money(amount) -> str:
    if not isinstance(amount, (int, float)) or amount <= 0:
        return ""
    if amount >= 1e9:
        return f"${amount / 1e9:,.2f}B"
    if amount >= 1e6:
        return f"${amount / 1e6:,.1f}M"
    return f"${amount:,.0f}"


def short_date(iso: str) -> str:
    try:
        d = dt.date.fromisoformat((iso or "")[:10])
    except ValueError:
        return iso or ""
    return f"{d.strftime('%b')} {d.day}"


_THE = {"United States", "United Kingdom", "Netherlands", "United Arab Emirates", "Czech Republic", "Czechia",
        "Philippines", "Dominican Republic", "Republic of Korea", "Russian Federation"}


def _country(name: str) -> str:
    return f"the {name}" if name in _THE else name


def a_form(form: str) -> str:
    """'an S-1', 'an 8-K', 'a D' - the article follows how the form name is spoken."""
    form = (form or "filing").strip()
    return f"an {form}" if form[:1].upper() in "AEFHILMNORSX8" else f"a {form}"


def _with_card(text: str, card: str) -> str:
    """Append the context card when it fits; otherwise keep the news and drop the card."""
    combined = f"{text} {card}".strip() if card else text
    return fit(combined) if x_length(combined) <= 280 else fit(text)


def draft(item: Item, card: str = "") -> str:
    extra = item.extra or {}
    k = item.kind
    if k == "form_d":
        sold = money(extra.get("total_amount_sold"))
        offered = money(extra.get("total_offering_amount"))
        investors = extra.get("investors_count")
        company = extra.get("company") or item.title
        amended = " amended" if extra.get("is_amendment") else ""
        what = f"{company} reports {sold} sold" if sold else f"{company} filed a private-offering notice"
        if offered and offered != sold:
            what += f" of {offered} offered"
        bits = [f"New SEC filing: {what} (Form D{amended}, filed {short_date(extra.get('filing_date', ''))})."]
        if extra.get("date_of_first_sale"):
            bits.append(f"First sale: {short_date(extra['date_of_first_sale'])}.")
        if investors:
            bits.append(f"{investors} investor{'s' if investors != 1 else ''}.")
        return _with_card(" ".join(bits), card)
    if k == "sec_filing":
        return _with_card(f"{extra.get('company', '')} filed {a_form(extra.get('form', 'new form'))} with the SEC "
                          f"({short_date(extra.get('filing_date', ''))}).", card)
    if k == "sec_mention":
        return _with_card(f"{extra.get('company', 'A company')} mentions brain-computer interfaces in "
                          f"{a_form(extra.get('form', 'SEC'))} filed {short_date(extra.get('filing_date', ''))}.", card)
    if k in ("trial_new", "trial_scope"):
        where = [_country(c) for c in (extra.get("countries") or [])[:3]]
        target = extra.get("enrollment")
        parts = [f"New implanted-BCI trial on ClinicalTrials.gov: {extra.get('title', '')}.",
                 f"Sponsor: {extra.get('sponsor', '')}."]
        if target:
            verb = f"Reports {target} enrolled" if extra.get("enrollment_type") == "ACTUAL" else f"Plans to enroll {target}"
            parts.append(verb + (f" in {', '.join(where)}." if where else "."))
        return _with_card(" ".join(parts), card)
    if k == "trial_status":
        new = STATUS_TEXT.get(extra.get("status", ""), extra.get("status", "").replace("_", " ").lower())
        return _with_card(f"Trial update: {extra.get('sponsor', '')}'s {extra.get('nct_id', '')} is now {new} "
                          f"({extra.get('title', '')}).", card)
    if k == "trial_enrollment":
        return _with_card(f"{extra.get('sponsor', '')} now reports {extra.get('enrollment')} "
                          f"{'people enrolled' if extra.get('enrollment_type') == 'ACTUAL' else 'as its enrollment target'} "
                          f"in {extra.get('nct_id', '')} ({extra.get('title', '')}).", card)
    if k in ("press", "news"):
        return _with_card(f"{extra.get('headline', item.title)}.", card)
    if k == "news_cn":
        return fit(f"From Chinese media ({extra.get('outlet', '')}): {extra.get('headline', item.title)}")
    if k in ("paper", "preprint"):
        venue = extra.get("venue", "")
        return _with_card(f"New in {venue}: {extra.get('headline', item.title)}." if venue else f"{item.title}.", card)
    if k in ("fda", "fedreg"):
        return _with_card(f"{extra.get('agency', 'FDA')}: {extra.get('headline', item.title)}.", card)
    if k == "fda_decision":
        return _with_card(f"FDA {extra.get('kind', 'decision')} {extra.get('id', '')}: {extra.get('device_name', '')} "
                          f"({extra.get('applicant', '')}), decided {short_date(extra.get('decision_date', ''))}.", card)
    if k == "job":
        return _with_card(f"{extra.get('company', '')} is hiring: {extra.get('job_title', '')} "
                          f"({extra.get('location', 'location not listed')}).", card)
    return fit(item.title)
