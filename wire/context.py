"""What the census already knows about a company, so every alert arrives with context.

The Wire reads the census the site publishes (docs/data/census.json and curated.json on
GitHub Pages), so a Monday rebuild or a curated fix reaches the alerts within the hour.
If the site can't be reached it falls back to the copy bundled with the deployment.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from census import config as census_config
from census.link import FALLBACK_PROGRAM, _alias_pattern

log = logging.getLogger(__name__)

_CACHE: dict = {"at": 0.0, "value": None}
CACHE_SECONDS = 3600


class Context:
    def __init__(self, census: dict, curated: dict):
        self.census = census or {}
        self.programs = list((curated or {}).get("programs") or [])
        self.overrides = dict((curated or {}).get("overrides") or {})
        self.fda_ids = set((curated or {}).get("fda_ids") or [])
        self.rows = {r["program"]: r for r in self.census.get("programs") or []}
        self.by_cik = {}
        for p in self.programs:
            if p.get("cik"):
                self.by_cik[str(int(p["cik"]))] = p["id"]

    # --- lookups -------------------------------------------------------
    def name(self, pid: str) -> str:
        for p in self.programs:
            if p["id"] == pid:
                return p.get("name") or pid
        row = self.rows.get(pid)
        return row["name"] if row else pid

    def program_for_text(self, *texts: str) -> str:
        hay = " " + " ".join(t.lower() for t in texts if t) + " "
        for p in self.programs:
            for alias in p.get("aliases") or []:
                if _alias_pattern(alias).search(hay):
                    return p["id"]
        return ""

    def program_for_cik(self, cik) -> str:
        try:
            return self.by_cik.get(str(int(cik)), "")
        except (TypeError, ValueError):
            return ""

    def aliases(self) -> list[str]:
        return [a for p in self.programs for a in (p.get("aliases") or [])]

    # --- the context card ---------------------------------------------
    def card(self, pid: str) -> str:
        if not pid or pid == FALLBACK_PROGRAM:
            return ""
        row = self.rows.get(pid)
        name = self.name(pid)
        if not row:
            return ""
        trials = row.get("trials_in_scope", 0)
        trial_txt = f"{trials} trial{'s' if trials != 1 else ''}"
        floor = row.get("floor") or 0
        if floor and trials:
            return f"{name}: {floor:,} verified implants and {trial_txt} in the BCI Census."
        if floor:  # no trial data (an offline build, or a program without registered trials)
            return f"{name}: {floor:,} verified implants in the BCI Census."
        if trials:
            return f"{name}: no verified implant count yet, {trial_txt} in the BCI Census."
        return f"{name}: tracked by the BCI Census, no verified implant count yet."


def _bundled(name: str) -> dict:
    path = Path(census_config.LATEST) / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load(session=None, site_url: str = "", now: float | None = None) -> Context:
    """Live census from the site when possible, cached for an hour; bundled copy otherwise."""
    now = time.time() if now is None else now
    if _CACHE["value"] is not None and now - _CACHE["at"] < CACHE_SECONDS:
        return _CACHE["value"]
    census, curated = {}, {}
    if session is not None and site_url:
        try:
            census = session.get(site_url + "data/census.json", timeout=8).json()
            curated = session.get(site_url + "data/curated.json", timeout=8).json()
        except Exception as exc:  # the site may not be published yet
            log.info("Using bundled census data (%s)", exc)
            census, curated = {}, {}
    if not census.get("programs") or not curated.get("programs"):
        census, curated = _bundled("census.json"), _bundled("curated.json")
    ctx = Context(census, curated)
    _CACHE.update(at=now, value=ctx)
    return ctx


def reset_cache() -> None:
    _CACHE.update(at=0.0, value=None)
