"""Attach trials, FDA decisions and filings to curated programs by alias."""

from __future__ import annotations

import re
from functools import lru_cache

from .util import norm_name

FALLBACK_PROGRAM = "academic-other"


def _haystack(*parts: str) -> str:
    return " " + " ".join(p.lower() for p in parts if p) + " "


@lru_cache(maxsize=None)
def _alias_pattern(alias: str) -> re.Pattern:
    """Match an alias as a whole word: "synchron" must not match "synchronous"; "braingate" matches "braingate2"."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias.lower()) + r"(?![a-z])")


def link_trial(trial: dict, programs: list[dict]) -> str:
    hay = _haystack(
        trial.get("sponsor", ""),
        " ".join(trial.get("collaborators") or []),
        trial.get("title", ""),
        trial.get("official_title", ""),
        " ".join(i.get("name", "") for i in trial.get("interventions") or []),
    )
    for program in programs:  # programs are listed in priority order
        for alias in program.get("aliases") or []:
            if _alias_pattern(alias).search(hay):
                return program["id"]
    return FALLBACK_PROGRAM


def link_fda(decision: dict, programs: list[dict]) -> str | None:
    applicant = norm_name(decision.get("applicant", ""))
    name = decision.get("device_name", "").lower()
    for program in programs:
        for fda_name in program.get("fda_applicants") or []:
            if norm_name(fda_name) and norm_name(fda_name) in applicant:
                return program["id"]
        for alias in program.get("aliases") or []:
            if len(alias) > 5 and _alias_pattern(alias).search(name):
                return program["id"]
    return None
