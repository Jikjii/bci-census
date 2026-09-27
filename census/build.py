"""Orchestrate a weekly run: pull, classify, count, diff, publish."""

from __future__ import annotations

import datetime as dt
import logging
import shutil

from . import config
from .curated import load_bundle, validate
from .diff import compute_changes, previous_snapshot
from .http import Throttle, make_session
from .link import link_fda, link_trial
from .post import build_thread, render_markdown
from .scope import classify
from .site import render
from .sources import clinicaltrials, edgar, openfda
from .tally import compute
from .util import read_json, write_csv, write_json

log = logging.getLogger(__name__)

TRIAL_COLUMNS = [
    "nct_id", "title", "program", "sponsor", "status", "enrollment", "enrollment_type", "implanted", "duration",
    "start_date", "primary_completion_date", "countries", "in_scope", "reason", "url", "last_update",
]
SNAPSHOT_TRIAL_FIELDS = [
    "nct_id", "title", "program", "sponsor", "status", "enrollment", "enrollment_type", "implanted", "duration",
    "in_scope", "reason", "start_date", "primary_completion_date", "completion_date", "countries", "url", "last_update",
]
PROGRAM_COLUMNS = [
    "program", "name", "company", "device", "approach", "hq_country", "floor", "basis",
    "registry_sum", "acute", "trials_in_scope", "trials_active",
]


def _pull(programs: list[dict], previous: dict) -> tuple[list[dict], list[dict], list[dict], dict]:
    status: dict[str, str] = {}
    session = make_session(config.DEFAULT_USER_AGENT)

    try:
        raw = clinicaltrials.fetch_studies(session, config.CTGOV_TERMS)
        trials = [clinicaltrials.normalize_study(r) for r in raw]
        status["clinicaltrials"] = f"ok: {len(trials)} studies reviewed"
    except Exception as exc:  # keep last week's data rather than publishing a hole
        log.error("ClinicalTrials.gov pull failed: %s", exc)
        trials = previous["trials"]
        status["clinicaltrials"] = f"failed, kept previous data: {exc}"

    applicants = sorted({a for p in programs for a in p.get("fda_applicants") or []})
    try:
        fda = openfda.fetch_decisions(session, applicants, config.FDA_DEVICE_KEYWORDS, config.openfda_api_key())
        status["openfda"] = f"ok: {len(fda)} decisions"
    except Exception as exc:
        log.error("openFDA pull failed: %s", exc)
        fda = previous["fda"]
        status["openfda"] = f"failed, kept previous data: {exc}"

    user_agent = config.sec_user_agent()
    if not user_agent:
        form_d = previous["form_d"]
        status["edgar"] = "skipped: set SEC_USER_AGENT to pull Form D filings"
    else:
        sec = make_session(user_agent)
        throttle = Throttle(0.15)
        form_d = []
        failures = []
        for program in programs:
            if not program.get("sec_names") and not program.get("cik"):
                continue
            try:
                form_d.extend(edgar.fetch_form_d(sec, program, throttle))
            except Exception as exc:
                failures.append(f"{program['id']}: {exc}")
                form_d.extend(f for f in previous["form_d"] if f.get("program") == program["id"])
        status["edgar"] = f"ok: {len(form_d)} filings" + (f"; failed for {', '.join(failures)}" if failures else "")
    return trials, fda, form_d, status


def run(offline: bool = False, as_of: str | None = None) -> dict:
    as_of = as_of or dt.date.today().isoformat()
    bundle = load_bundle(config.CURATED)
    errors = validate(bundle)
    if errors:
        raise SystemExit("Curated data has problems:\n  " + "\n  ".join(errors))
    programs = bundle["programs"]
    overrides = bundle["overrides"]

    previous = {
        "trials": read_json(config.LATEST / "trials_all.json", default=[]),
        "fda": read_json(config.LATEST / "fda.json", default=[]),
        "form_d": read_json(config.LATEST / "form_d.json", default=[]),
    }
    if offline:
        trials, fda, form_d = previous["trials"], previous["fda"], previous["form_d"]
        sources = {"mode": "offline: reused the last pulled data"}
    else:
        trials, fda, form_d, sources = _pull(programs, previous)

    for trial in trials:
        trial.update(classify(trial, overrides))
        manual = overrides.get(trial["nct_id"]) or {}
        trial["program"] = (manual.get("program") or link_trial(trial, programs)) if trial["in_scope"] else ""
        trial.pop("implanted", None)
        trial.pop("implanted_source", None)
        if manual.get("implanted") is not None:
            trial["implanted"] = int(manual["implanted"])
            trial["implanted_source"] = manual.get("source_url", "")
    for decision in fda:
        decision["program"] = link_fda(decision, programs)

    census = compute(bundle, trials, as_of)
    census["sources"] = sources

    fact_ids = {kind: sorted(f["id"] for f in bundle[kind]) for kind in ("counts", "regulatory", "funding")}
    current = {"census": census, "trials": trials, "fda": fda, "form_d": form_d, "fact_ids": fact_ids}
    changes = compute_changes(previous_snapshot(config.SNAPSHOTS, as_of), current)

    in_scope = [t for t in trials if t["in_scope"]]
    events = [
        {"date": e["date"], "program": e["program"], "event": e["event"], "tier": e["tier"], "source_url": e["source_url"]}
        for e in bundle["regulatory"]
    ] + [
        {"date": d["decision_date"], "program": d["program"], "event": f'{d["kind"]} {d["id"]}: {d["device_name"]}', "tier": "A", "source_url": d["url"]}
        for d in fda
        if d.get("program") and d["id"] not in {e.get("fda_id") for e in bundle["regulatory"]}
    ]
    funding = [
        {"date": f["date"], "program": f["program"], "event": f["event"], "amount_usd": f.get("amount_usd"), "tier": f["tier"], "source_url": f["source_url"]}
        for f in bundle["funding"]
    ] + [
        {"date": f["filing_date"], "program": f["program"], "event": f'Form {f["form"]} ({f["company"]})', "amount_usd": f.get("total_amount_sold"), "tier": "A", "source_url": f["url"]}
        for f in form_d
    ]

    curated_export = {
        "programs": programs,
        "overrides": overrides,
        "fda_ids": sorted({e["fda_id"] for e in bundle["regulatory"] if e.get("fda_id")}),
    }
    outputs = {
        "census.json": census,
        "curated.json": curated_export,
        "trials.json": in_scope,
        "trials_all.json": trials,
        "fda.json": fda,
        "form_d.json": form_d,
        "changes.json": changes,
        "fact_ids.json": fact_ids,
    }
    for name, data in outputs.items():
        write_json(config.LATEST / name, data)
    # Snapshots keep what the weekly diff needs, not the full trial text.
    snapshot_dir = config.SNAPSHOTS / as_of
    slim = dict(outputs, **{"trials_all.json": [{k: t.get(k) for k in SNAPSHOT_TRIAL_FIELDS if k in t} for t in trials]})
    slim["trials.json"] = [t for t in slim["trials_all.json"] if t.get("in_scope")]
    slim.pop("curated.json", None)  # curated data lives in git history already
    for name, data in slim.items():
        write_json(snapshot_dir / name, data)

    write_csv(config.LATEST / "programs.csv", census["programs"], PROGRAM_COLUMNS)
    write_csv(config.LATEST / "trials.csv", in_scope, TRIAL_COLUMNS)
    write_csv(config.LATEST / "trials_all.csv", trials, TRIAL_COLUMNS)
    write_csv(config.LATEST / "events.csv", events, ["date", "program", "event", "tier", "source_url"])
    write_csv(config.LATEST / "funding.csv", funding, ["date", "program", "event", "amount_usd", "tier", "source_url"])

    config.DOCS.mkdir(parents=True, exist_ok=True)
    (config.DOCS / "index.html").write_text(
        render(census, trials, fda, form_d, changes, bundle, config.SITE_URL, config.REPO_URL, config.X_HANDLE),
        encoding="utf-8",
    )
    (config.DOCS / ".nojekyll").write_text("", encoding="utf-8")
    docs_data = config.DOCS / "data"
    docs_data.mkdir(parents=True, exist_ok=True)
    for path in config.LATEST.iterdir():
        if path.suffix in (".json", ".csv"):
            shutil.copy2(path, docs_data / path.name)

    posts = build_thread(census, changes, config.SITE_URL, config.REPO_URL, as_of, trials_tracked=len(in_scope))
    config.POSTS.mkdir(parents=True, exist_ok=True)
    (config.POSTS / f"{as_of}.md").write_text(render_markdown(posts, as_of), encoding="utf-8")

    log.info("Census %s: floor %s across %s programs; %d in-scope trials; %d changes",
             as_of, census["total_floor"], census["programs_counted"], len(in_scope), len(changes["items"]))
    return {"census": census, "changes": changes, "posts": posts}
