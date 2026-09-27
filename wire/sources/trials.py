"""ClinicalTrials.gov: new implanted-BCI trials, status changes and enrollment changes.

The first run stores a snapshot of every matching trial (about 630 records). After that it
asks only for records updated in the last three days and compares them with the snapshot,
using the same classifier as the census so the Wire and the site never disagree.
"""

from __future__ import annotations

import datetime as dt

from census import config as census_config
from census.link import FALLBACK_PROGRAM, link_trial
from census.scope import classify
from census.sources.clinicaltrials import API, build_query, normalize_study

from ..drafts import STATUS_TEXT
from ..items import HIGH, NORMAL, URGENT, Item
from . import Source

SNAPSHOT_KEY = "trials"


def _short(title: str, limit: int = 90) -> str:
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


class ClinicalTrials(Source):
    name = "trials"
    every = 60
    description = "ClinicalTrials.gov: new implanted-BCI trials, status and enrollment changes"

    def fetch(self, session, extra: dict, max_pages: int = 40) -> list[dict]:
        params = {"query.term": build_query(census_config.CTGOV_TERMS), "pageSize": 200, "format": "json", **extra}
        studies, token = [], None
        for _ in range(max_pages):
            if token:
                params["pageToken"] = token
            resp = session.get(API, params=params, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
            studies.extend(payload.get("studies") or [])
            token = payload.get("nextPageToken")
            if not token:
                break
        return [normalize_study(s) for s in studies]

    def poll(self, env) -> list[Item]:
        record = env.state.get(SNAPSHOT_KEY) or {}
        snapshot = record.get("trials") or {}
        first = not snapshot
        if first:
            trials = self.fetch(env.session, {})
        else:
            since = (env.now.date() - dt.timedelta(days=3)).isoformat()
            trials = self.fetch(env.session, {"filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{since},MAX]"})

        items = []
        for trial in trials:
            result = classify(trial, env.ctx.overrides)
            forced = (env.ctx.overrides.get(trial["nct_id"]) or {}).get("program")
            pid = (forced or link_trial(trial, env.ctx.programs)) if result["in_scope"] else ""
            before = snapshot.get(trial["nct_id"])
            now = {"s": trial["status"], "n": trial["enrollment"], "t": trial["enrollment_type"],
                   "in": result["in_scope"], "p": pid, "d": result["duration"]}
            snapshot[trial["nct_id"]] = now
            if first or not result["in_scope"]:
                continue
            items.extend(self._changes(trial, result, pid, before, now))

        env.state.put(SNAPSHOT_KEY, {"trials": snapshot, "updated": env.now.isoformat(timespec="seconds")})
        return items

    def _changes(self, trial: dict, result: dict, pid: str, before: dict | None, now: dict) -> list[Item]:
        nct = trial["nct_id"]
        tracked = bool(pid) and pid != FALLBACK_PROGRAM
        temporary = result["duration"] == "acute"
        target = f"{trial['enrollment']} ({(trial['enrollment_type'] or '').lower()})" if trial["enrollment"] is not None else "n/a"
        facts = (f"{nct} · {trial['sponsor']} · {STATUS_TEXT.get(trial['status'], trial['status'].lower())} · "
                 f"enrollment {target}" + (f" · {', '.join(trial['countries'][:4])}" if trial["countries"] else "")
                 + (" · temporary implant" if temporary else ""))
        extra = {"nct_id": nct, "title": _short(trial["title"], 110), "sponsor": trial["sponsor"],
                 "status": trial["status"], "enrollment": trial["enrollment"],
                 "enrollment_type": trial["enrollment_type"], "countries": trial["countries"]}
        title = f"{trial['sponsor']}: {_short(trial['title'], 80)}"

        def item(key: str, kind: str, priority: int) -> Item:
            return Item(source=self.name, key=key, kind=kind, title=title, url=trial["url"],
                        published=trial.get("last_update", ""), program=pid, priority=priority,
                        summary=facts, extra=dict(extra))

        if before is None:
            return [item(f"{nct}:new", "trial_new", NORMAL if temporary else (URGENT if tracked else HIGH))]
        if not before.get("in"):
            return [item(f"{nct}:scope", "trial_scope", NORMAL if temporary else HIGH)]
        out = []
        if before.get("s") != now["s"]:
            out.append(item(f"{nct}:status:{now['s']}", "trial_status", NORMAL if temporary else HIGH))
        if (before.get("n"), before.get("t")) != (now["n"], now["t"]):
            out.append(item(f"{nct}:enroll:{now['n']}:{now['t']}", "trial_enrollment",
                            HIGH if now["t"] == "ACTUAL" and not temporary else NORMAL))
        return out
