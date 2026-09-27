"""End-to-end tests for the Wire, with every source served from fixtures (no network)."""

import copy
import datetime as dt
import json
import urllib.parse

import pytest

from census.post import x_length
from wire import context as context_mod
from wire import runner as runner_mod
from wire.config import Settings
from wire.context import Context
from wire.feeds import parse_feed
from wire.httpclient import Response
from wire.items import Item
from wire.notify import NtfyNotifier, PrintNotifier, for_item
from wire.sources import news as news_mod
from wire.state import DynamoState, FileState

from conftest import FIXTURES

W = FIXTURES / "wire"
DAY = dt.datetime(2026, 9, 26, 16, 0, tzinfo=dt.timezone.utc)  # noon in New York
NIGHT = dt.datetime(2026, 9, 27, 6, 0, tzinfo=dt.timezone.utc)  # 2 am in New York
MORNING = dt.datetime(2026, 9, 27, 11, 1, tzinfo=dt.timezone.utc)  # 7:01 am in New York
EMPTY_RSS = b'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title></channel></rss>'
EMPTY_ATOM = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'


def read(name: str) -> bytes:
    return (W / name).read_bytes()


class FakeWeb:
    """Serves each source from fixtures. Flip `full` to switch from the seeding view to the news view."""

    def __init__(self):
        self.full = False
        self.fail = set()
        self.calls = []
        self.posts = []
        ct = json.loads((FIXTURES / "ctgov_studies.json").read_text())
        self.trials_full = ct
        changed = copy.deepcopy(ct["studies"])
        changed[0]["protocolSection"]["statusModule"]["overallStatus"] = "ACTIVE_NOT_RECRUITING"
        new = copy.deepcopy(ct["studies"][7])
        new["protocolSection"]["identificationModule"]["nctId"] = "NCT90000009"
        self.trials_recent = {"studies": [changed[0], new]}
        self.jobs = json.loads(read("greenhouse_neuralink.json"))

    def respond(self, url: str, params: dict) -> tuple[int, bytes]:
        host = urllib.parse.urlsplit(url).hostname
        if host in self.fail:
            return 500, b"server error"
        if "browse-edgar" in url:
            if params.get("CIK") == "0001708503":
                return 200, read("edgar_neuralink.atom")
            if params.get("CIK") == "0009999999":
                return 200, read("edgar_examplix.atom") if self.full else EMPTY_ATOM
            return 200, EMPTY_ATOM
        if url.endswith("primary_doc.xml"):
            return 200, (FIXTURES / "form_d.xml").read_bytes()
        if host == "efts.sec.gov":
            return 200, read("edgar_fts.json") if self.full else b'{"hits": {"hits": []}}'
        if host == "news.google.com":
            name = "gnews_zh.xml" if params.get("hl") == "zh-CN" else "gnews_en.xml"
            return 200, read(name) if self.full else EMPTY_RSS
        if host == "www.nature.com" and url.endswith("/nature.rss"):
            return 200, read("nature.rdf") if self.full else EMPTY_RSS
        if host == "www.fda.gov":
            return 200, EMPTY_RSS
        if host == "clinicaltrials.gov":
            payload = self.trials_recent if "filter.advanced" in params else self.trials_full
            return 200, json.dumps(payload).encode()
        if host == "www.federalregister.gov":
            return 200, read("fedreg.json") if self.full else b'{"results": []}'
        if host == "eutils.ncbi.nlm.nih.gov":
            if "esearch" in url:
                return 200, read("pubmed_esearch.json") if self.full else b'{"esearchresult": {"idlist": []}}'
            return 200, read("pubmed_esummary.json")
        if host == "api.biorxiv.org":
            if "/biorxiv/" in url and self.full:
                return 200, read("biorxiv.json")
            return 200, b'{"messages": [{"total": "0"}], "collection": []}'
        if host == "boards-api.greenhouse.io":
            return 200, json.dumps(self.jobs).encode()
        return 404, b"not found"

    # the Session interface the Wire uses
    def get(self, url, params=None, timeout=None, headers=None):
        params = {k: str(v) for k, v in (params or {}).items()}
        self.calls.append((url, params))
        status, body = self.respond(url, params)
        return Response(status, body, url, {"content-type": "application/octet-stream"})

    def post_json(self, url, payload, headers=None, timeout=None):
        self.posts.append((url, payload, headers))
        return Response(200, b"{}", url, {})


@pytest.fixture
def ctx(bundle):
    programs = [{"id": "examplix", "name": "Examplix", "aliases": ["examplix"], "cik": 9999999,
                 "fda_applicants": ["Examplix"]}] + bundle["programs"]
    census = {"programs": [
        {"program": "examplix", "name": "Examplix", "floor": 12, "trials_in_scope": 3},
        {"program": "neuralink", "name": "Neuralink", "floor": 21, "trials_in_scope": 6},
        {"program": "braingate", "name": "BrainGate", "floor": 0, "trials_in_scope": 5},
    ]}
    return Context(census, {"programs": programs, "overrides": {}})


@pytest.fixture
def wire(tmp_path, ctx, monkeypatch):
    monkeypatch.setattr(runner_mod.context_mod, "load", lambda session, site_url: ctx)
    monkeypatch.setattr(news_mod, "TIER_ONE", news_mod.TIER_ONE + ("tier1.example.org",))
    web = FakeWeb()
    settings = Settings(sec_user_agent="BCI Census test@example.com", state_path=str(tmp_path / "state.json"))
    state = FileState(settings.state_path)
    notifier = PrintNotifier(echo=False)
    return runner_mod.Runner(settings, state, web, notifier), web, notifier, state


def _titles(notifier):
    return [n.title for n in notifier.sent]


def test_feeds_parse_all_three_formats():
    atom = parse_feed(read("edgar_neuralink.atom"))
    assert atom[0].extra["accession-number"] == "0001708503-25-000003" and atom[0].extra["filing-type"] == "D"
    assert atom[0].published == "2025-06-12T20:16:44+00:00"
    rss = parse_feed(read("gnews_en.xml"))
    assert rss[0].source_url == "https://www.globenewswire.com" and rss[0].published == "2026-09-26T12:30:00+00:00"
    rdf = parse_feed(read("nature.rdf"))
    assert rdf[0].id == "https://journal.example.org/articles/test-1" and rdf[0].published.startswith("2026-09-30")
    assert "intracortical brain-computer interface" in rdf[0].summary


def test_first_run_records_everything_without_alerts(wire):
    runner, web, notifier, state = wire
    web.full = True  # even with news present, the first run only records it
    report = runner.run(now=DAY, force=True)
    assert not report["errors"], report["errors"]
    assert len(notifier.sent) == 1 and notifier.sent[0].title.startswith("BCI Wire is watching 12 new sources")
    assert all(p["seeded"] for p in report["polled"])
    assert state.get("trials")["trials"]["NCT90000001"]["s"] == "RECRUITING"


def test_new_items_route_by_priority(wire):
    runner, web, notifier, state = wire
    runner.run(now=DAY, force=True)  # seed with the quiet view
    notifier.sent.clear()
    web.full = True
    web.jobs["jobs"].append({"absolute_url": "https://boards.greenhouse.io/neuralink/jobs/1", "id": 1,
                             "title": "Clinical Research Associate", "location": {"name": "Toronto, Ontario, Canada"},
                             "first_published": "2026-09-26T09:00:00-04:00"})
    report = runner.run(now=DAY + dt.timedelta(minutes=5), force=True)
    assert not report["errors"], report["errors"]
    sent = {n.title: n for n in notifier.sent}
    titles = list(sent)

    form_d = next(n for t, n in sent.items() if t.startswith("Form D: Examplix"))
    assert form_d.priority == 5 and "$" in form_d.message
    assert form_d.actions[0][0] == "Draft post" and form_d.actions[0][1].startswith("https://twitter.com/intent/tweet?text=")
    assert any(t.startswith("Press release: Examplix Announces") for t in titles)          # company release: ring
    assert any(t.startswith("News: Brain implant startup draws") for t in titles)           # major outlet: push
    assert not any("Examplix brain chip explained" in t for t in titles)                    # small blog: digest
    assert not any("bakery" in t for t in titles)                                           # irrelevant: dropped
    assert any(t.startswith("China: 示例医疗") for t in titles)                               # approval keyword
    assert any(t.startswith("SEC mention: CLEARONE INC") for t in titles)
    assert not any("SEC mention: Examplix" in t for t in titles)                            # tracked: covered by its feed
    assert any(t.startswith("Paper: Nature: A test speech neuroprosthesis") for t in titles)
    assert any(t.startswith("Federal Register:") for t in titles)
    assert any(t.startswith("Trial status: ") for t in titles)
    assert any(t.startswith("New trial: ") for t in titles)
    job = next(n for t, n in sent.items() if t.startswith("Hiring: Neuralink: Clinical Research Associate"))
    assert "New location for Neuralink: Toronto, Ontario, Canada" in job.message

    queued = [d["title"] for d in state.get("digest")["items"]]
    assert any("Examplix brain chip explained" in t for t in queued)
    assert any("脑机接口产业发展前景展望" in t for t in queued)
    assert any("intracortical microelectrode array stability" in t for t in queued)       # PubMed
    assert any("closed-loop intracortical brain-computer interface" in t for t in queued)  # bioRxiv

    # the same news is never sent twice
    notifier.sent.clear()
    runner.run(now=DAY + dt.timedelta(minutes=10), force=True)
    assert notifier.sent == []


def test_drafts_fit_x_and_leave_the_link_for_the_reply(wire):
    runner, web, notifier, state = wire
    runner.run(now=DAY, force=True)
    web.full = True
    runner.run(now=DAY + dt.timedelta(minutes=5), force=True)
    drafts = [n.message.split("Draft (", 1)[1] for n in notifier.sent if "Draft (" in n.message]
    assert len(drafts) >= 8
    for text in drafts:
        count, draft = text.split("/280): ", 1)
        draft = draft.split("\n\nLink for your reply:")[0]
        assert x_length(draft) <= 280 and int(count) == x_length(draft)
        assert "http" not in draft


def test_quiet_hours_hold_alerts_for_the_morning_digest(wire):
    runner, web, notifier, state = wire
    runner.run(now=DAY, force=True)
    notifier.sent.clear()
    web.full = True
    runner.run(now=NIGHT, force=True)
    assert notifier.sent == []  # nothing rings at 2 am
    held = len(state.get("digest")["items"])
    assert held >= 10
    runner.run(now=MORNING)
    digest = notifier.sent[-1]
    assert digest.title == f"BCI Wire morning digest: {held} items"
    assert "Overnight in BCI:" in digest.message and digest.actions[0][0] == "Draft post"
    assert state.get("digest")["items"] == []
    runner.run(now=MORNING + dt.timedelta(minutes=1))  # no second digest in the same slot
    assert sum(1 for n in notifier.sent if "digest" in n.title) == 1


def test_sources_keep_their_own_schedule(wire):
    runner, web, notifier, state = wire
    runner.run(now=DAY, force=True)
    before = len(web.calls)
    report = runner.run(now=DAY + dt.timedelta(seconds=30))
    assert report["polled"] == [] and len(web.calls) == before
    report = runner.run(now=DAY + dt.timedelta(minutes=1))
    assert [p["source"] for p in report["polled"]] == ["edgar_companies"]
    report = runner.run(now=DAY + dt.timedelta(minutes=3))
    assert {p["source"] for p in report["polled"]} == {"edgar_companies", "news_en"}


def test_a_failing_source_alerts_once(wire):
    runner, web, notifier, state = wire
    runner.run(now=DAY, force=True)
    notifier.sent.clear()
    web.fail.add("www.federalregister.gov")
    for n in range(7):
        runner.run(now=DAY + dt.timedelta(minutes=10 * (n + 1)), force=True, only={"fedreg"})
    health = [n for n in notifier.sent if n.title.startswith("Wire health")]
    assert len(health) == 1 and "failed 5 times in a row" in health[0].title
    assert "HTTP 500" in health[0].message


def test_sec_sources_wait_for_a_contact_email(wire):
    runner, web, notifier, state = wire
    runner.settings.sec_user_agent = ""
    runner.run(now=DAY, force=True)
    runner.run(now=DAY + dt.timedelta(minutes=5), force=True)
    warnings = [n for n in notifier.sent if "SEC_USER_AGENT" in n.title]
    assert len(warnings) == 2  # one per SEC source, never repeated
    assert not any("sec.gov" in url for url, _ in web.calls)


def test_ntfy_payload():
    web = FakeWeb()
    item = Item(source="t", key="k", kind="form_d", title="Examplix filed Form D", url="https://example.org/f",
                priority=5, summary="x" * 5000, draft="Test draft")
    NtfyNotifier(web, "https://ntfy.sh", "bci-wire-test", token="tok").send(for_item(item, card="Examplix: context."))
    url, payload, headers = web.posts[0]
    assert url == "https://ntfy.sh/" and payload["topic"] == "bci-wire-test" and payload["priority"] == 5
    assert payload["click"] == "https://example.org/f" and payload["actions"][0]["label"] == "Draft post"
    assert len(payload["message"].encode()) <= 3800 and headers == {"Authorization": "Bearer tok"}


def test_file_state_round_trip(tmp_path):
    state = FileState(tmp_path / "s.json")
    state.put("a", {"x": 1})
    assert FileState(tmp_path / "s.json").get("a") == {"x": 1}


class FakeTable:
    def __init__(self):
        self.items = {}

    def get_item(self, Key):
        item = self.items.get(Key["pk"])
        return {"Item": item} if item else {}

    def put_item(self, Item, ConditionExpression=None, ExpressionAttributeValues=None):
        current = self.items.get(Item["pk"])
        if ConditionExpression and current and current.get("expires_at", 0) >= ExpressionAttributeValues[":now"]:
            raise type("ConditionalCheckFailedException", (Exception,), {})("conditional check failed")
        self.items[Item["pk"]] = Item

    def delete_item(self, Key, **kwargs):
        self.items.pop(Key["pk"], None)


def test_dynamo_state_and_lock():
    state = DynamoState("t", table=FakeTable())
    state.put("src#x", {"seen": ["a"]}, ttl_days=1)
    assert state.get("src#x") == {"seen": ["a"]}
    assert state.acquire_lock("one", 60) is True
    assert state.acquire_lock("two", 60) is False  # a second run waits its turn
    state.release_lock("one")
    assert state.acquire_lock("two", 60) is True


def test_lambda_handler_runs_once(tmp_path, monkeypatch, ctx):
    from wire import lambda_handler

    web = FakeWeb()
    monkeypatch.setattr(lambda_handler, "Session", lambda *a, **k: web)
    monkeypatch.setattr(runner_mod.context_mod, "load", lambda session, site_url: ctx)
    monkeypatch.setenv("WIRE_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("SEC_USER_AGENT", "BCI Census test@example.com")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("WIRE_TABLE", raising=False)
    report = lambda_handler.handler({"force": True})
    assert report["errors"] == {} and len(report["polled"]) == 12


def test_context_card_and_lookup(ctx):
    assert ctx.card("examplix") == "Examplix: 12 verified implants and 3 trials in the BCI Census."
    assert ctx.card("braingate") == "BrainGate: no verified implant count yet, 5 trials in the BCI Census."
    assert ctx.program_for_cik("0001708503") == "neuralink"
    assert ctx.program_for_text("Why Examplix matters") == "examplix"


def test_bundled_context_loads_without_network():
    context_mod.reset_cache()
    ctx = context_mod.load(session=None, site_url="")
    assert ctx.programs and ctx.card("neuralink").startswith("Neuralink: 21 verified implants")
    context_mod.reset_cache()
