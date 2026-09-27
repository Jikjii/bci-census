"""What changed since the previous weekly snapshot."""

from __future__ import annotations

from pathlib import Path

from .util import read_json

FACT_KINDS = ("counts", "regulatory", "funding")
BASIS_TEXT = {"sourced": "from a sourced count", "registry": "from ClinicalTrials.gov actual enrollment", "none": "no sourced count"}


def load_snapshot(folder: Path) -> dict | None:
    census = read_json(folder / "census.json")
    if census is None:
        return None
    return {
        "census": census,
        "trials": read_json(folder / "trials_all.json", default=[]),
        "fda": read_json(folder / "fda.json", default=[]),
        "form_d": read_json(folder / "form_d.json", default=[]),
        "fact_ids": read_json(folder / "fact_ids.json", default={}),
    }


def previous_snapshot(snapshots_dir: Path, as_of: str) -> dict | None:
    if not snapshots_dir.exists():
        return None
    earlier = sorted(p for p in snapshots_dir.iterdir() if p.is_dir() and p.name < as_of)
    for folder in reversed(earlier):
        snap = load_snapshot(folder)
        if snap:
            return snap
    return None


def _trial_item(kind: str, trial: dict, detail: str) -> dict:
    return {
        "kind": kind,
        "program": trial.get("program", ""),
        "title": f"{trial.get('nct_id')}: {trial.get('title', '')}",
        "detail": detail,
        "url": trial.get("url", ""),
    }


def compute_changes(prev: dict | None, cur: dict) -> dict:
    if not prev:
        return {"first_run": True, "since": None, "floor_before": None, "floor_after": cur["census"]["total_floor"], "items": []}

    items: list[dict] = []
    before = {t["nct_id"]: t for t in prev["trials"] if t.get("in_scope")}
    after = {t["nct_id"]: t for t in cur["trials"] if t.get("in_scope")}

    # The first live pull after a seed-only build would list every trial as "new". Summarize it instead.
    if not prev["trials"] and after:
        items.append({"kind": "first_pull", "program": "", "title": f"{len(after)} implanted BCI trials from ClinicalTrials.gov",
                      "detail": "", "url": ""})
        after_iter: dict = {}
    else:
        after_iter = after

    for nct, trial in after_iter.items():
        old = before.get(nct)
        if not old:
            items.append(_trial_item("new_trial", trial, f"New {trial.get('duration', '')} BCI trial, {trial.get('status', '').replace('_', ' ').lower()}"))
            continue
        if old.get("status") != trial.get("status"):
            items.append(
                _trial_item(
                    "status_change",
                    trial,
                    f"Status: {old.get('status', '').replace('_', ' ').lower()} → {trial.get('status', '').replace('_', ' ').lower()}",
                )
            )
        if (old.get("enrollment"), old.get("enrollment_type")) != (trial.get("enrollment"), trial.get("enrollment_type")):
            items.append(
                _trial_item(
                    "enrollment_change",
                    trial,
                    f"Enrollment: {old.get('enrollment')} ({(old.get('enrollment_type') or '').lower()}) → "
                    f"{trial.get('enrollment')} ({(trial.get('enrollment_type') or '').lower()})",
                )
            )
    for nct in sorted(before.keys() - after.keys()):
        items.append(_trial_item("trial_dropped", before[nct], "No longer classified as an implanted BCI trial"))

    prev_rows = {r["program"]: r for r in prev["census"].get("programs") or []}
    floor_items = []
    for row in cur["census"]["programs"]:
        before_floor = (prev_rows.get(row["program"]) or {}).get("floor", 0)
        if row["floor"] != before_floor:
            floor_items.append(
                {
                    "kind": "floor_change",
                    "program": row["program"],
                    "title": f"{row['name']} {before_floor} → {row['floor']}",
                    "detail": BASIS_TEXT.get(row.get("basis", ""), ""),
                    "url": "",
                }
            )
    items[:0] = floor_items  # floor changes lead the list

    old_fda = {d["id"] for d in prev["fda"]}
    linked_fda = [d for d in cur["fda"] if d.get("program")]
    if not prev["fda"] and linked_fda:
        items.append({"kind": "first_pull", "program": "", "title": f"{len(linked_fda)} FDA decisions from openFDA",
                      "detail": "", "url": ""})
        linked_fda = []
    for decision in linked_fda:
        if decision["id"] not in old_fda:
            items.append(
                {
                    "kind": "fda_decision",
                    "program": decision["program"],
                    "title": f"{decision['kind']} {decision['id']}: {decision.get('device_name', '')}",
                    "detail": f"{decision.get('applicant', '')}, decided {decision.get('decision_date', '')}",
                    "url": decision.get("url", ""),
                }
            )

    old_filings = {f["id"] for f in prev["form_d"]}
    new_filings = list(cur["form_d"])
    if not prev["form_d"] and new_filings:
        items.append({"kind": "first_pull", "program": "", "title": f"{len(new_filings)} SEC Form D filings from EDGAR",
                      "detail": "", "url": ""})
        new_filings = []
    for filing in new_filings:
        if filing["id"] not in old_filings:
            sold = filing.get("total_amount_sold")
            amount = f"${sold / 1e6:,.1f}M sold" if isinstance(sold, (int, float)) and sold else "amount not stated"
            items.append(
                {
                    "kind": "form_d",
                    "program": filing.get("program", ""),
                    "title": f"Form {filing.get('form', 'D')} filed by {filing.get('company', '')}",
                    "detail": f"{amount}, filed {filing.get('filing_date', '')}",
                    "url": filing.get("url", ""),
                }
            )

    old_facts = prev.get("fact_ids") or {}
    new_facts = cur.get("fact_ids") or {}
    for kind in FACT_KINDS:
        for fact_id in sorted(set(new_facts.get(kind, [])) - set(old_facts.get(kind, []))):
            items.append({"kind": f"fact_{kind}", "program": "", "title": fact_id, "detail": "New sourced fact", "url": ""})

    return {
        "first_run": False,
        "since": prev["census"].get("as_of"),
        "floor_before": prev["census"].get("total_floor"),
        "floor_after": cur["census"]["total_floor"],
        "items": items,
    }
