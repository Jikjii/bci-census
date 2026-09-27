"""Paths, environment settings and search terms."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CURATED = DATA / "curated"
LATEST = DATA / "latest"
SNAPSHOTS = DATA / "snapshots"
DOCS = ROOT / "docs"
POSTS = ROOT / "posts"

SITE_URL = os.environ.get("CENSUS_SITE_URL", "https://jikjii.github.io/bci-census/")
REPO_URL = os.environ.get("CENSUS_REPO_URL", "https://github.com/jikjii/bci-census")
X_HANDLE = os.environ.get("CENSUS_X_HANDLE", "SiegeGrell")

DEFAULT_USER_AGENT = "BCI-Census/0.1 (+https://github.com/jikjii/bci-census)"


def sec_user_agent() -> str:
    """SEC EDGAR requires a descriptive User-Agent with a contact email."""
    return os.environ.get("SEC_USER_AGENT", "").strip()


def openfda_api_key() -> str:
    return os.environ.get("OPENFDA_API_KEY", "").strip()


# Retrieval is deliberately broad. census.scope decides what actually counts.
CTGOV_TERMS = [
    "brain-computer interface",
    "brain computer interface",
    "brain-machine interface",
    "brain machine interface",
    "intracortical",
    "neuroprosthesis",
    "neuroprosthetic",
    "neural interface",
    "microelectrode array",
    "Utah array",
    "speech neuroprosthesis",
    "Stentrode",
    "BrainGate",
    "Neuralink",
    "Paradromics",
    "Connexus",
    "Precision Neuroscience",
    "NeuroPort",
    "WIMAGINE",
    "Synchron",
]

# Searched against openFDA 510(k) device names, in addition to each program's applicants.
FDA_DEVICE_KEYWORDS = [
    "brain-computer interface",
    "brain computer interface",
    "cortical interface",
    "neural interface",
]
