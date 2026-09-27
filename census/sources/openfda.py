"""openFDA device endpoints: 510(k) clearances and PMA approvals."""

from __future__ import annotations

import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the Wire runs these parsers without third-party packages
    import requests

from ..util import norm_date

log = logging.getLogger(__name__)

BASE = "https://api.fda.gov/device"


def _query(session: requests.Session, endpoint: str, search: str, api_key: str = "", limit: int = 100) -> list[dict]:
    params = {"search": search, "limit": limit}
    if api_key:
        params["api_key"] = api_key
    resp = session.get(f"{BASE}/{endpoint}.json", params=params, timeout=60)
    if resp.status_code == 404:  # openFDA answers 404 when nothing matches
        return []
    resp.raise_for_status()
    return resp.json().get("results") or []


def normalize_510k(rec: dict) -> dict:
    k = rec.get("k_number") or ""
    return {
        "id": k,
        "kind": "510(k)",
        "applicant": rec.get("applicant") or "",
        "device_name": rec.get("device_name") or "",
        "decision_date": norm_date(rec.get("decision_date")),
        "decision": rec.get("decision_description") or rec.get("decision_code") or "",
        "product_code": rec.get("product_code") or "",
        "url": f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID={k}" if k else "",
    }


def normalize_pma(rec: dict) -> dict:
    pma = rec.get("pma_number") or ""
    supplement = rec.get("supplement_number") or ""
    ident = f"{pma}{supplement}" if supplement else pma
    return {
        "id": ident,
        "kind": "PMA supplement" if supplement else "PMA",
        "applicant": rec.get("applicant") or "",
        "device_name": rec.get("trade_name") or rec.get("generic_name") or "",
        "decision_date": norm_date(rec.get("decision_date")),
        "decision": rec.get("decision_code") or "",
        "product_code": rec.get("product_code") or "",
        "url": f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id={ident}" if ident else "",
    }


def fetch_decisions(
    session: requests.Session, applicants: list[str], keywords: list[str], api_key: str = ""
) -> list[dict]:
    found: dict[str, dict] = {}
    for applicant in applicants:
        for rec in _query(session, "510k", f'applicant:"{applicant}"', api_key):
            item = normalize_510k(rec)
            found[item["id"]] = item
        for rec in _query(session, "pma", f'applicant:"{applicant}"', api_key):
            item = normalize_pma(rec)
            found[item["id"]] = item
    for keyword in keywords:
        for rec in _query(session, "510k", f'device_name:"{keyword}"', api_key):
            item = normalize_510k(rec)
            found[item["id"]] = item
    log.info("openFDA: %d decisions", len(found))
    return sorted(found.values(), key=lambda d: d["decision_date"], reverse=True)
