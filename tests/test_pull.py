"""Exercise the live-pull code paths against a fake HTTP session shaped like the real APIs."""

import json

from census.http import Throttle
from census.sources import clinicaltrials, edgar, openfda

from conftest import FIXTURES


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text if text else json.dumps(payload or {})

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, routes):
        self.routes = routes  # list of (predicate, response or callable)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        for predicate, response in self.routes:
            if predicate(url, params or {}):
                return response(url, params or {}) if callable(response) else response
        return FakeResponse(404, {"error": {"code": "NOT_FOUND"}})


def test_clinicaltrials_paginates():
    studies = json.loads((FIXTURES / "ctgov_studies.json").read_text())["studies"]
    pages = {None: {"studies": studies[:5], "nextPageToken": "abc", "totalCount": 8},
             "abc": {"studies": studies[5:], "totalCount": 8}}
    session = FakeSession([(lambda u, p: u == clinicaltrials.API, lambda u, p: FakeResponse(200, pages[p.get("pageToken")]))])
    got = clinicaltrials.fetch_studies(session, ["brain-computer interface"])
    assert len(got) == 8
    assert session.calls[0][1]["query.term"] == '"brain-computer interface"'
    assert session.calls[1][1]["pageToken"] == "abc"


def test_openfda_handles_no_match_and_dedupes():
    result = json.loads((FIXTURES / "openfda_510k.json").read_text())
    session = FakeSession([
        (lambda u, p: u.endswith("/510k.json") and "Precision" in p["search"], FakeResponse(200, result)),
        (lambda u, p: u.endswith("/510k.json") and "cortical interface" in p["search"], FakeResponse(200, result)),
    ])
    decisions = openfda.fetch_decisions(session, ["Precision Neuroscience", "Synchron"], ["cortical interface"])
    assert [d["id"] for d in decisions] == ["K000001"]  # same K number from two queries, kept once


def test_edgar_end_to_end():
    efts = {"hits": {"hits": [
        {"_source": {"ciks": ["0009999999"], "display_names": ["Example Neuro Inc.  (CIK 0009999999)"]}},
        {"_source": {"ciks": ["0001111111"], "display_names": ["Example Neurology Partners LLC  (CIK 0001111111)"]}},
    ]}}
    submissions = {"name": "Example Neuro Inc.", "filings": {"recent": {
        "form": ["D", "10-K", "D/A"],
        "accessionNumber": ["0009999999-26-000001", "0009999999-26-000002", "0009999999-26-000003"],
        "filingDate": ["2026-03-10", "2026-03-11", "2026-04-01"],
    }}}
    xml = (FIXTURES / "form_d.xml").read_text()
    session = FakeSession([
        (lambda u, p: u == edgar.FULL_TEXT_SEARCH, FakeResponse(200, efts)),
        (lambda u, p: u.startswith("https://data.sec.gov/submissions/CIK0009999999"), FakeResponse(200, submissions)),
        (lambda u, p: u.endswith("/primary_doc.xml"), FakeResponse(200, text=xml)),
    ])
    program = {"id": "example", "sec_names": ["Example Neuro Inc"], "cik": None}
    filings = edgar.fetch_form_d(session, program, Throttle(0))
    assert [f["form"] for f in filings] == ["D", "D/A"]
    assert filings[0]["total_amount_sold"] == 55_000_000
    assert filings[0]["url"].endswith("/000999999926000001/0009999999-26-000001-index.htm")
    assert filings[0]["cik"] == "0009999999"
