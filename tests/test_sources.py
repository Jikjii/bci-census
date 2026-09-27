import json

from census.link import link_fda
from census.sources.clinicaltrials import build_query
from census.sources.edgar import _names_match, parse_form_d
from census.sources.openfda import normalize_510k, normalize_pma

from conftest import FIXTURES


def test_normalize_study(trials):
    t = next(t for t in trials if t["nct_id"] == "NCT90000008")
    assert t["enrollment"] == 15
    assert t["enrollment_type"] == "ACTUAL"
    assert t["countries"] == ["United States"]  # de-duplicated
    assert t["collaborators"] == ["Massachusetts General Hospital"]
    assert t["url"] == "https://clinicaltrials.gov/study/NCT90000008"
    assert t["start_date"] == "2009-05"


def test_build_query_quotes_phrases():
    q = build_query(["brain-computer interface", "Neuralink", "Utah array"])
    assert q == '"brain-computer interface" OR Neuralink OR "Utah array"'


def test_openfda_normalize_and_link(bundle):
    rec = json.loads((FIXTURES / "openfda_510k.json").read_text())["results"][0]
    d = normalize_510k(rec)
    assert d["id"] == "K000001" and d["decision_date"] == "2025-04-11"
    assert "pmn.cfm?ID=K000001" in d["url"]
    assert link_fda(d, bundle["programs"]) == "precision"


def test_openfda_pma_supplement_and_compact_dates():
    d = normalize_pma({"pma_number": "P000001", "supplement_number": "S002", "decision_date": "20250102", "trade_name": "X"})
    assert d["id"] == "P000001S002" and d["kind"] == "PMA supplement" and d["decision_date"] == "2025-01-02"


def test_parse_form_d():
    parsed = parse_form_d((FIXTURES / "form_d.xml").read_text())
    assert parsed["entity_name"] == "Example Neuro Inc."
    assert parsed["date_of_first_sale"] == "2026-03-02"
    assert parsed["total_amount_sold"] == 55_000_000
    assert parsed["total_offering_amount"] == 60_000_000
    assert parsed["investors_count"] == 14
    assert parsed["is_amendment"] is False
    assert set(parsed["security_types"]) == {"equity", "optiontoacquire"}
    assert parsed["related_persons"][0] == {"name": "Ada Example", "roles": ["Executive Officer", "Director"]}


def test_edgar_name_matching():
    assert _names_match("Neuralink Corp", "Neuralink Corp.  (CIK 0001234567)")
    assert _names_match("Synchron Inc", "SYNCHRON, INC.  (CIK 0000000001)")
    assert not _names_match("Synchron Inc", "Synchronoss Technologies Inc (CIK 0001131554)")
    assert _names_match("Neuralink Corp", "Neuralink Corp /DE/  (CIK 0001708503)")
    assert not _names_match("Blackrock Neurotech", "Blackrock Neurotech SPV - Allocations Funds LLC  (CIK 0001966910)")
