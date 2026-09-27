"""The census math: a verified floor per program and in total."""

from __future__ import annotations

import datetime as dt

from .link import FALLBACK_PROGRAM
from .util import date_key

COUNTED_TIERS = {"A", "B", "C"}
ACTIVE_STATUSES = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING"}
# Registry counts need a current trial: participants of long-finished trials may have had devices removed.
FOLLOW_UP_STATUSES = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION", "SUSPENDED"}
ENDED_STATUSES = {"COMPLETED", "TERMINATED"}
RECENT_YEARS = 5


def _to_date(value) -> dt.date | None:
    key = date_key(value or "")
    try:
        return dt.date.fromisoformat(key.replace("-00", "-01"))
    except ValueError:
        return None


def registry_count(trial: dict, as_of: str) -> int:
    """People a trial adds to its program's registry count.

    Chronic, in scope, with actual enrollment (or a sourced implanted count from
    trial_overrides.yaml), and either still in follow-up or ended within RECENT_YEARS.
    """
    if not trial.get("in_scope") or trial.get("duration") != "chronic":
        return 0
    n = trial.get("implanted")
    if n is None:
        if trial.get("enrollment_type") != "ACTUAL":
            return 0
        n = trial.get("enrollment") or 0
    if not n:
        return 0
    status = trial.get("status")
    if status in FOLLOW_UP_STATUSES:
        return int(n)
    if status in ENDED_STATUSES:
        ended = _to_date(trial.get("completion_date") or trial.get("primary_completion_date"))
        ref = _to_date(as_of)
        if ended and ref and (ref - ended).days <= RECENT_YEARS * 365.25:
            return int(n)
    return 0

FALLBACK_META = {
    "id": FALLBACK_PROGRAM,
    "name": "Academic and other",
    "company": "Universities and hospitals",
    "device": "Various",
    "approach": "Various",
    "hq_country": "",
}


def _latest(facts: list[dict]) -> dict | None:
    return max(facts, key=lambda f: date_key(f["as_of"])) if facts else None


def compute(bundle: dict, trials: list[dict], as_of: str) -> dict:
    programs = list(bundle["programs"]) + [FALLBACK_META]
    counts = [f for f in bundle["counts"] if f.get("tier") in COUNTED_TIERS]
    rows = []
    for program in programs:
        pid = program["id"]
        facts = [f for f in counts if f["program"] == pid]
        chronic_fact = _latest([f for f in facts if f["measure"] == "chronic_implanted"])
        acute_fact = _latest([f for f in facts if f["measure"] == "acute_procedures"])
        unspecified_fact = _latest([f for f in facts if f["measure"] == "unspecified_implanted"])

        in_scope = [t for t in trials if t.get("in_scope") and t.get("program") == pid]
        counted = [(t, registry_count(t, as_of)) for t in in_scope]
        counted = [(t, n) for t, n in counted if n > 0]
        acute_actual = [
            t
            for t in in_scope
            if t.get("duration") == "acute" and t.get("enrollment_type") == "ACTUAL" and t.get("enrollment")
        ]
        registry_sum = sum(n for _, n in counted)
        sourced = int(chronic_fact["value"]) if chronic_fact else 0

        # Company counts already include trial participants, so take the larger number, never the sum.
        if chronic_fact and sourced >= registry_sum:
            floor, basis = sourced, "sourced"
        elif registry_sum:
            floor, basis = registry_sum, "registry"
        else:
            floor, basis = 0, "none"

        acute = max(int(acute_fact["value"]) if acute_fact else 0, sum(int(t["enrollment"]) for t in acute_actual))
        rows.append(
            {
                "program": pid,
                "name": program["name"],
                "company": program.get("company", ""),
                "device": program.get("device", ""),
                "approach": program.get("approach", ""),
                "hq_country": program.get("hq_country", ""),
                "floor": floor,
                "basis": basis,
                "sourced_fact": chronic_fact,
                "registry_sum": registry_sum,
                "registry_trials": [t["nct_id"] for t, _ in counted],
                "registry_detail": [{"nct_id": t["nct_id"], "count": n, "sourced": t.get("implanted") is not None} for t, n in counted],
                "acute": acute,
                "acute_fact": acute_fact,
                "unspecified_fact": unspecified_fact,
                "trials_in_scope": len(in_scope),
                "trials_active": sum(1 for t in in_scope if t.get("status") in ACTIVE_STATUSES),
            }
        )

    rows.sort(key=lambda r: (-r["floor"], r["name"]))
    other = [f for f in bundle["other_counts"]]
    other_values = [int(f["value"]) for f in other if isinstance(f.get("value"), (int, float))]
    return {
        "as_of": as_of,
        "total_floor": sum(r["floor"] for r in rows),
        "programs_counted": sum(1 for r in rows if r["floor"] > 0),
        "acute_total": sum(r["acute"] for r in rows),
        "programs": rows,
        "other_counts": other,
        "other_range": [min(other_values), max(other_values)] if other_values else None,
        "verify_queue": bundle["verify_queue"],
    }
