"""Load and validate the hand-verified facts in data/curated/."""

from __future__ import annotations

from pathlib import Path

import yaml

from .util import norm_date

FILES = {
    "programs": "programs.yaml",
    "counts": "implant_counts.yaml",
    "other_counts": "other_counts.yaml",
    "regulatory": "regulatory_events.yaml",
    "funding": "funding_rounds.yaml",
    "overrides": "trial_overrides.yaml",
    "verify_queue": "verify_queue.yaml",
}

TIERS = {"A", "B", "C", "D"}
MEASURES = {"chronic_implanted", "acute_procedures", "unspecified_implanted"}
SPECIAL_PROGRAMS = {"academic-other", "ecosystem", "policy"}


def _load(path: Path):
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_bundle(curated_dir: Path) -> dict:
    bundle: dict = {}
    for key, filename in FILES.items():
        data = _load(curated_dir / filename)
        if key == "overrides":
            bundle[key] = (data or {}).get("overrides") or {}
        else:
            bundle[key] = data or []
    for key in ("counts", "other_counts", "regulatory", "funding", "verify_queue"):
        for fact in bundle[key]:
            for field in ("as_of", "date", "checked_on", "added_on"):
                if field in fact:
                    fact[field] = norm_date(fact[field])
    return bundle


def validate(bundle: dict) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    program_ids = {p.get("id") for p in bundle["programs"]} | SPECIAL_PROGRAMS

    for program in bundle["programs"]:
        for key in ("id", "name", "aliases"):
            if not program.get(key):
                errors.append(f"programs.yaml: {program.get('id', '?')} is missing '{key}'")

    def check(kind: str, fact: dict, required: list[str]) -> None:
        ident = fact.get("id", "?")
        for key in required:
            if fact.get(key) in (None, ""):
                errors.append(f"{kind}: {ident} is missing '{key}'")
        if ident in seen:
            errors.append(f"{kind}: duplicate id {ident}")
        seen.add(ident)
        if fact.get("tier") and fact["tier"] not in TIERS:
            errors.append(f"{kind}: {ident} has unknown tier {fact['tier']!r}")
        if "program" in fact and fact["program"] not in program_ids:
            errors.append(f"{kind}: {ident} points at unknown program {fact['program']!r}")
        url = str(fact.get("source_url", ""))
        if url and not url.startswith(("http://", "https://")):
            errors.append(f"{kind}: {ident} has a malformed source_url")

    for fact in bundle["counts"]:
        check("implant_counts", fact, ["id", "program", "measure", "value", "as_of", "tier", "source_url"])
        if fact.get("measure") not in MEASURES:
            errors.append(f"implant_counts: {fact.get('id')} has unknown measure {fact.get('measure')!r}")
    for fact in bundle["other_counts"]:
        check("other_counts", fact, ["id", "label", "value", "as_of", "tier", "source_url"])
    for fact in bundle["regulatory"]:
        check("regulatory_events", fact, ["id", "program", "date", "event", "tier", "source_url"])
    for fact in bundle["funding"]:
        check("funding_rounds", fact, ["id", "program", "date", "event", "tier", "source_url"])
    for item in bundle["verify_queue"]:
        if not item.get("id") or not item.get("claim"):
            errors.append(f"verify_queue: entry needs 'id' and 'claim': {item}")
    for nct, override in bundle["overrides"].items():
        if not isinstance(override, dict) or not set(override) & {"in_scope", "duration", "program", "implanted"}:
            errors.append(f"trial_overrides: {nct} needs in_scope, duration, program or implanted")
            continue
        if override.get("duration") not in (None, "acute", "chronic"):
            errors.append(f"trial_overrides: {nct} has unknown duration {override['duration']!r}")
        if override.get("program") and override["program"] not in program_ids:
            errors.append(f"trial_overrides: {nct} points at unknown program {override['program']!r}")
        if "implanted" in override:
            if not isinstance(override["implanted"], int) or override["implanted"] < 0:
                errors.append(f"trial_overrides: {nct} needs a whole number for 'implanted'")
            if not str(override.get("source_url", "")).startswith(("http://", "https://")):
                errors.append(f"trial_overrides: {nct} sets 'implanted' without a source_url")
        if not override.get("reason"):
            errors.append(f"trial_overrides: {nct} needs a 'reason'")
    return errors
