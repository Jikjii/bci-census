import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def ctgov_payload():
    return json.loads((FIXTURES / "ctgov_studies.json").read_text())


@pytest.fixture
def trials(ctgov_payload):
    from census.sources.clinicaltrials import normalize_study

    return [normalize_study(s) for s in ctgov_payload["studies"]]


@pytest.fixture
def bundle():
    from census.config import CURATED
    from census.curated import load_bundle

    return load_bundle(CURATED)
