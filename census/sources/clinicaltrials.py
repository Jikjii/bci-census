"""ClinicalTrials.gov API v2: search and normalize studies."""

from __future__ import annotations

import logging
from typing import Any

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the Wire runs these parsers without third-party packages
    import requests

from ..util import norm_date

log = logging.getLogger(__name__)

API = "https://clinicaltrials.gov/api/v2/studies"


def build_query(terms: list[str]) -> str:
    """Essie expression: quote multi-word or hyphenated terms, join with OR."""
    parts = []
    for term in terms:
        term = term.strip()
        if not term:
            continue
        parts.append(f'"{term}"' if (" " in term or "-" in term) else term)
    return " OR ".join(parts)


def fetch_studies(
    session: requests.Session, terms: list[str], page_size: int = 200, max_pages: int = 40
) -> list[dict]:
    params: dict[str, Any] = {
        "query.term": build_query(terms),
        "pageSize": page_size,
        "countTotal": "true",
        "format": "json",
    }
    studies: list[dict] = []
    token = None
    for page in range(max_pages):
        if token:
            params["pageToken"] = token
        resp = session.get(API, params=params, timeout=90)
        resp.raise_for_status()
        payload = resp.json()
        if page == 0:
            log.info("ClinicalTrials.gov: %s matching studies", payload.get("totalCount", "?"))
        studies.extend(payload.get("studies") or [])
        token = payload.get("nextPageToken")
        if not token:
            break
    return studies


def _dig(obj: Any, *path: str, default: Any = None) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key)
        if obj is None:
            return default
    return obj


def normalize_study(raw: dict) -> dict:
    ps = raw.get("protocolSection") or {}
    ident = ps.get("identificationModule") or {}
    status = ps.get("statusModule") or {}
    sponsors = ps.get("sponsorCollaboratorsModule") or {}
    design = ps.get("designModule") or {}
    conditions = ps.get("conditionsModule") or {}
    arms = ps.get("armsInterventionsModule") or {}
    locations = ps.get("contactsLocationsModule") or {}
    description = ps.get("descriptionModule") or {}

    nct = ident.get("nctId", "")
    enrollment = design.get("enrollmentInfo") or {}
    interventions = [
        {
            "type": (item.get("type") or "").upper(),
            "name": item.get("name") or "",
            "description": item.get("description") or "",
        }
        for item in (arms.get("interventions") or [])
    ]
    countries = sorted(
        {loc.get("country") for loc in (locations.get("locations") or []) if loc.get("country")}
    )
    count = enrollment.get("count")
    return {
        "nct_id": nct,
        "title": ident.get("briefTitle") or ident.get("officialTitle") or "",
        "official_title": ident.get("officialTitle") or "",
        "sponsor": _dig(sponsors, "leadSponsor", "name", default=""),
        "collaborators": [c.get("name") for c in (sponsors.get("collaborators") or []) if c.get("name")],
        "status": status.get("overallStatus") or "",
        "study_type": design.get("studyType") or "",
        "phases": design.get("phases") or [],
        "enrollment": int(count) if isinstance(count, (int, float)) else None,
        "enrollment_type": (enrollment.get("type") or "").upper(),
        "start_date": norm_date(_dig(status, "startDateStruct", "date", default="")),
        "primary_completion_date": norm_date(_dig(status, "primaryCompletionDateStruct", "date", default="")),
        "completion_date": norm_date(_dig(status, "completionDateStruct", "date", default="")),
        "last_update": norm_date(_dig(status, "lastUpdatePostDateStruct", "date", default="")),
        "conditions": conditions.get("conditions") or [],
        "keywords": conditions.get("keywords") or [],
        "interventions": interventions,
        "countries": countries,
        "summary": description.get("briefSummary") or "",
        "details": description.get("detailedDescription") or "",
        "url": f"https://clinicaltrials.gov/study/{nct}" if nct else "",
    }
