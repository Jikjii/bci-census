"""SEC EDGAR: find tracked companies' Form D filings and parse the offering amounts.

SEC's fair-access policy requires a User-Agent with a contact email and at most
10 requests per second. Set SEC_USER_AGENT, for example "BCI Census you@example.com".
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the Wire runs these parsers without third-party packages
    import requests

from ..http import Throttle
from ..util import norm_date, norm_name

log = logging.getLogger(__name__)

FULL_TEXT_SEARCH = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_DIR = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}"


def _names_match(wanted: str, display_name: str) -> bool:
    """EDGAR display names look like 'Neuralink Corp  (CIK 0001234567)'."""
    shown = norm_name(re.sub(r"\(CIK[^)]*\)", "", display_name or ""))
    target = norm_name(wanted)
    if not target or not shown.startswith(target):
        return False
    rest = shown[len(target):].strip()
    return rest == "" or bool(re.fullmatch(r"[a-z]{2}", rest))  # e.g. "Neuralink Corp /DE/"


def resolve_cik(session: requests.Session, company_name: str, throttle: Throttle) -> str | None:
    throttle.wait()
    resp = session.get(FULL_TEXT_SEARCH, params={"q": f'"{company_name}"', "forms": "D"}, timeout=60)
    if resp.status_code != 200:
        log.warning("EDGAR search failed for %s: HTTP %s", company_name, resp.status_code)
        return None
    hits = (resp.json().get("hits") or {}).get("hits") or []
    votes: Counter[str] = Counter()
    for hit in hits:
        src = hit.get("_source") or {}
        for cik, shown in zip(src.get("ciks") or [], src.get("display_names") or []):
            if _names_match(company_name, shown):
                votes[str(cik).zfill(10)] += 1
    return votes.most_common(1)[0][0] if votes else None


def list_form_d(session: requests.Session, cik: str, throttle: Throttle, since: str = "2012-01-01") -> tuple[str, list[dict]]:
    throttle.wait()
    resp = session.get(SUBMISSIONS.format(cik=str(cik).zfill(10)), timeout=60)
    resp.raise_for_status()
    data = resp.json()
    recent = (data.get("filings") or {}).get("recent") or {}
    rows = []
    for form, acc, filed in zip(recent.get("form") or [], recent.get("accessionNumber") or [], recent.get("filingDate") or []):
        if form in ("D", "D/A") and filed >= since:
            rows.append({"form": form, "accession": acc, "filing_date": filed})
    return data.get("name") or "", rows


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_text(root: ET.Element, *names: str) -> str:
    """First matching descendant text, ignoring XML namespaces."""
    wanted = set(names)
    for el in root.iter():
        if _local(el.tag) in wanted and el.text and el.text.strip():
            return el.text.strip()
    return ""


def _to_number(value: str) -> float | str | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return value  # e.g. "Indefinite"


def parse_form_d(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    security_types = []
    for el in root.iter():
        name = _local(el.tag)
        if name.startswith("is") and name.endswith("Type") and (el.text or "").strip().lower() == "true":
            security_types.append(name[2:-4].lower())
    related = []
    for person in root.iter():
        if _local(person.tag) != "relatedPersonInfo":
            continue
        first = _find_text(person, "firstName")
        last = _find_text(person, "lastName")
        roles = [(r.text or "").strip() for r in person.iter() if _local(r.tag) == "relationship" and r.text]
        related.append({"name": " ".join(p for p in (first, last) if p), "roles": roles})
    investors = _find_text(root, "totalNumberAlreadyInvested")
    return {
        "entity_name": _find_text(root, "entityName"),
        "jurisdiction": _find_text(root, "jurisdictionOfInc"),
        "industry_group": _find_text(root, "industryGroupType"),
        "is_amendment": _find_text(root, "isAmendment").lower() == "true",
        "date_of_first_sale": norm_date(_first_sale(root)),
        "total_offering_amount": _to_number(_find_text(root, "totalOfferingAmount")),
        "total_amount_sold": _to_number(_find_text(root, "totalAmountSold")),
        "total_remaining": _to_number(_find_text(root, "totalRemaining")),
        "investors_count": int(investors) if investors.isdigit() else None,
        "security_types": security_types,
        "related_persons": related,
    }


def _first_sale(root: ET.Element) -> str:
    for el in root.iter():
        if _local(el.tag) == "dateOfFirstSale":
            return _find_text(el, "value")
    return ""


def fetch_form_d(
    session: requests.Session, program: dict, throttle: Throttle, since: str = "2012-01-01"
) -> list[dict]:
    """All Form D filings for one program's company, parsed."""
    names = program.get("sec_names") or []
    cik = str(program["cik"]).zfill(10) if program.get("cik") else None
    if not cik:
        for name in names:
            cik = resolve_cik(session, name, throttle)
            if cik:
                break
    if not cik:
        log.info("EDGAR: no Form D issuer found for %s", program["id"])
        return []
    company, filings = list_form_d(session, cik, throttle, since)
    out = []
    for filing in filings:
        acc_nodash = filing["accession"].replace("-", "")
        folder = ARCHIVE_DIR.format(cik_int=int(cik), acc_nodash=acc_nodash)
        throttle.wait()
        resp = session.get(f"{folder}/primary_doc.xml", timeout=60)
        if resp.status_code != 200:
            log.warning("EDGAR: could not read %s (HTTP %s)", filing["accession"], resp.status_code)
            continue
        try:
            parsed = parse_form_d(resp.text)
        except ET.ParseError as exc:
            log.warning("EDGAR: bad XML in %s: %s", filing["accession"], exc)
            continue
        out.append(
            {
                "id": filing["accession"],
                "program": program["id"],
                "cik": cik,
                "company": parsed["entity_name"] or company,
                "form": filing["form"],
                "filing_date": filing["filing_date"],
                "date_of_first_sale": parsed["date_of_first_sale"],
                "total_offering_amount": parsed["total_offering_amount"],
                "total_amount_sold": parsed["total_amount_sold"],
                "total_remaining": parsed["total_remaining"],
                "investors_count": parsed["investors_count"],
                "security_types": parsed["security_types"],
                "url": f"{folder}/{filing['accession']}-index.htm",
            }
        )
    log.info("EDGAR: %s -> %d Form D filings", program["id"], len(out))
    return out
