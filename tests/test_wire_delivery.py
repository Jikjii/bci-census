"""How alerts reach the phone (Telegram, ntfy, both) and local time without tzdata."""

import datetime as dt
import json

import pytest

from wire import runner as runner_mod
from wire import tz
from wire.config import Settings
from wire.context import Context
from wire.httpclient import HTTPError, OutOfTime, Response, Session, redact
from wire.items import Item
from wire.notify import (FanOut, Notification, NotifyError, NtfyNotifier, PrintNotifier, TelegramNotifier,
                         build_notifier, digest, for_item)

TOKEN = "123456:SECRET-token"


class FakeTelegram:
    """Answers like the Bot API. `replies` is a queue of (status, body) for successive posts."""

    def __init__(self, replies=None, raise_with=None):
        self.replies = list(replies or [])
        self.raise_with = raise_with
        self.posts = []

    def post_json(self, url, payload, headers=None, timeout=None):
        self.posts.append((url, json.loads(json.dumps(payload))))
        if self.raise_with:
            raise self.raise_with
        status, body = self.replies.pop(0) if self.replies else (200, {"ok": True, "result": {"message_id": 1}})
        return Response(status, json.dumps(body).encode(), url, {"content-type": "application/json"})


def _item(**kw):
    base = dict(source="t", key="k", kind="form_d", title="Examplix filed Form D <amended>", priority=5,
                url="https://www.sec.gov/Archives/edgar/data/1/2/primary_doc.xml",
                summary="Examplix Form D: $5.0M sold; first sale 2026-09-20 & 3 investors.",
                draft="Examplix raised $5.0M (Form D, Sep 20).\n\nExamplix: 12 verified implants.")
    base.update(kw)
    return Item(**base)


def test_telegram_message_formats_the_draft_to_copy():
    web = FakeTelegram()
    TelegramNotifier(web, TOKEN, "42").send(for_item(_item(), card="Examplix: 12 verified implants."))
    url, payload = web.posts[0]
    assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert payload["chat_id"] == "42" and payload["parse_mode"] == "HTML"
    assert payload["disable_notification"] is False and payload["link_preview_options"] == {"is_disabled": True}
    text = payload["text"]
    assert text.startswith("<b>URGENT: Form D: Examplix filed Form D &lt;amended&gt;</b>")
    assert "&amp; 3 investors" in text and "Context: Examplix: 12 verified implants." in text
    assert "<pre>Examplix raised $5.0M (Form D, Sep 20).\n\nExamplix: 12 verified implants.</pre>" in text
    assert text.count("Examplix raised") == 1  # the draft appears once, in the copy block
    assert "Link for your reply: https://www.sec.gov/" in text
    labels = [b["text"] for b in payload["reply_markup"]["inline_keyboard"][0]]
    assert labels == ["Draft post", "Open source"]


def test_telegram_digest_keeps_list_and_draft():
    items = [_item(key=str(n), title=f"Story {n}", priority=2, kind="news") for n in range(3)]
    web = FakeTelegram()
    TelegramNotifier(web, TOKEN, "42").send(digest(items, "morning digest", "Overnight in BCI:\n1) Story 0"))
    text = web.posts[0][1]["text"]
    assert web.posts[0][1]["disable_notification"] is True  # digests arrive quietly
    assert text.startswith("<b>BCI Wire morning digest: 3 items</b>")
    assert "1. [News] Story 0" in text and text.endswith("<pre>Overnight in BCI:\n1) Story 0</pre>")


def test_telegram_drops_buttons_it_rejects_instead_of_the_alert():
    web = FakeTelegram(replies=[(400, {"ok": False, "description": "Bad Request: BUTTON_URL_INVALID"}),
                                (200, {"ok": True, "result": {}})])
    TelegramNotifier(web, TOKEN, "42").send(for_item(_item()))
    assert "reply_markup" in web.posts[0][1] and "reply_markup" not in web.posts[1][1]


def test_telegram_errors_never_contain_the_token():
    web = FakeTelegram(raise_with=HTTPError(f"URLError: timed out for https://api.telegram.org/bot{TOKEN}/sendMessage"))
    with pytest.raises(NotifyError) as err:
        TelegramNotifier(web, TOKEN, "42").send(Notification(title="t", message="m"))
    assert TOKEN not in str(err.value) and "<token>" in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__

    web = FakeTelegram(replies=[(401, {"ok": False, "description": "Unauthorized"})])
    with pytest.raises(NotifyError) as err:
        TelegramNotifier(web, TOKEN, "42").send(Notification(title="t", message="m"))
    assert "HTTP 401 Unauthorized" in str(err.value) and TOKEN not in str(err.value)


def test_telegram_setup_lists_chats():
    updates = [{"update_id": 1, "message": {"chat": {"id": 987654321, "first_name": "Ada", "type": "private"}}},
               {"update_id": 2, "message": {"chat": {"id": 987654321, "first_name": "Ada", "type": "private"}}}]
    web = FakeTelegram(replies=[(200, {"ok": True, "result": updates})])
    assert TelegramNotifier(web, TOKEN, "").chats() == [("987654321", "Ada")]


def test_build_notifier_uses_what_is_configured():
    web = FakeTelegram()
    both = Settings(telegram_token=TOKEN, telegram_chat_id="42", ntfy_topic="bci-wire-x")
    assert isinstance(build_notifier(Settings(telegram_token=TOKEN, telegram_chat_id="42"), web), TelegramNotifier)
    assert isinstance(build_notifier(Settings(ntfy_topic="bci-wire-x"), web), NtfyNotifier)
    assert isinstance(build_notifier(both, web), FanOut)
    assert isinstance(build_notifier(Settings(telegram_token=TOKEN), web), PrintNotifier)  # no chat id yet
    assert isinstance(build_notifier(both, web, dry_run=True), PrintNotifier)
    env = Settings.from_env({"TELEGRAM_BOT_TOKEN": f" {TOKEN} ", "TELEGRAM_CHAT_ID": "42"})
    assert env.telegram_token == TOKEN and env.telegram_chat_id == "42"


def test_fanout_succeeds_if_any_channel_does():
    class Broken:
        def send(self, note):
            raise RuntimeError("down")

    ok = PrintNotifier(echo=False)
    FanOut([Broken(), ok]).send(Notification(title="t", message="m"))
    assert len(ok.sent) == 1
    with pytest.raises(RuntimeError):
        FanOut([Broken(), Broken()]).send(Notification(title="t", message="m"))


def test_lambda_test_and_status_events(tmp_path, monkeypatch):
    from wire import lambda_handler

    web = FakeTelegram()
    monkeypatch.setattr(lambda_handler, "Session", lambda *a, **k: web)
    monkeypatch.setenv("WIRE_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("WIRE_TABLE", raising=False)
    assert lambda_handler.handler({"test": True}) == {"test": "sent", "channel": "TelegramNotifier"}
    assert "BCI Wire test" in web.posts[0][1]["text"]
    status = lambda_handler.handler({"status": True})
    assert status["edgar_companies"] == {"last_run": None, "last_ok": None, "fail_count": None, "last_error": None}
    assert status["digest_queue"] == 0


def test_context_card_without_trial_data():
    ctx = Context({"programs": [{"program": "a", "name": "A", "floor": 21, "trials_in_scope": 0},
                                {"program": "b", "name": "B", "floor": 0, "trials_in_scope": 0}]},
                  {"programs": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]})
    assert ctx.card("a") == "A: 21 verified implants in the BCI Census."
    assert ctx.card("b") == "B: tracked by the BCI Census, no verified implant count yet."


@pytest.mark.parametrize("name", ["America/New_York", "America/Los_Angeles", "Europe/Stockholm", "Europe/London",
                                  "Asia/Shanghai"])
def test_fallback_zones_match_the_tz_database(name):
    real, rule = tz.zone(name), tz.zone(name, use_system=False)
    assert isinstance(rule, tz.RuleZone)
    moment = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    while moment.year < 2028:  # every hour for two years, across all four DST switches
        assert moment.astimezone(rule).replace(tzinfo=None) == moment.astimezone(real).replace(tzinfo=None), moment
        moment += dt.timedelta(hours=1)
    summer = dt.datetime(2026, 7, 1, 12, tzinfo=rule)
    assert summer.utcoffset() == dt.datetime(2026, 7, 1, 12, tzinfo=real).utcoffset()


def test_quiet_hours_hold_without_tzdata(monkeypatch):
    monkeypatch.setattr(tz, "zone", lambda name, use_system=True: tz.RuleZone(name, *tz.RULES[name]))
    runner_mod.local_zone.cache_clear()
    try:
        settings = Settings()
        assert runner_mod.is_quiet(settings, dt.datetime(2026, 9, 27, 6, 0, tzinfo=dt.timezone.utc))  # 2 am NY
        assert not runner_mod.is_quiet(settings, dt.datetime(2026, 9, 26, 16, 0, tzinfo=dt.timezone.utc))  # noon
        assert runner_mod.is_quiet(settings, dt.datetime(2026, 12, 1, 4, 30, tzinfo=dt.timezone.utc))  # 11:30 pm EST
        assert not runner_mod.is_quiet(settings, dt.datetime(2026, 12, 1, 12, 5, tzinfo=dt.timezone.utc))  # 7:05 am
    finally:
        runner_mod.local_zone.cache_clear()


def test_urls_in_errors_hide_keys_and_tokens():
    url = "https://api.fda.gov/device/510k.json?search=applicant:%22x%22&api_key=SECRET1&limit=1"
    assert "SECRET1" not in redact(url) and "limit=1" in redact(url)
    assert redact(f"https://api.telegram.org/bot{TOKEN}/sendMessage") == "https://api.telegram.org/bot<token>/sendMessage"
    assert Response(403, b"", url).status_code == 403
    with pytest.raises(HTTPError) as err:
        Response(403, b"", url).raise_for_status()
    assert "SECRET1" not in str(err.value)


def test_no_request_starts_after_the_deadline():
    import time

    session = Session("ua", deadline=time.monotonic() - 1)
    with pytest.raises(OutOfTime):
        session.get("https://www.example.org/feed")  # raises before any connection is made


def test_running_out_of_time_defers_instead_of_failing(tmp_path):
    from wire.sources import Source
    from wire.state import FileState

    class Slow(Source):
        name, every = "slow", 5

        def poll(self, env):
            raise OutOfTime("out of time for https://www.example.org/")

    state = FileState(tmp_path / "s.json")
    runner = runner_mod.Runner(Settings(), state, FakeTelegram(), PrintNotifier(echo=False), sources=[Slow()])
    runner_mod.context_mod.reset_cache()
    report = runner.run(now=dt.datetime(2026, 9, 26, 16, tzinfo=dt.timezone.utc))
    assert report["deferred"] == ["slow"] and report["errors"] == {}
    assert state.get("src#slow") is None  # no failure counted, and it is due again next minute


def test_lambda_budgets_against_its_remaining_time(tmp_path, monkeypatch):
    import time

    from wire import lambda_handler

    web = FakeTelegram()
    monkeypatch.setattr(lambda_handler, "Session", lambda *a, **k: web)
    monkeypatch.setenv("WIRE_STATE_PATH", str(tmp_path / "state.json"))
    for key in ("WIRE_TABLE", "NTFY_TOPIC", "TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(key, raising=False)

    class Context:
        def get_remaining_time_in_millis(self):
            return 120_000

    lambda_handler.handler({"test": True}, Context())
    assert 105 < web.deadline - time.monotonic() <= 110


def test_digest_draft_puts_english_headlines_first():
    items = [Item(source="n", key="1", kind="news_cn", title="脑机接口新进展", priority=4),
             Item(source="n", key="2", kind="news", title="Brain implant maker files to go public", priority=4),
             Item(source="n", key="3", kind="job", title="Hiring in Austin", priority=4)]
    draft = runner_mod.Runner.digest_draft(items, morning=True)
    assert draft == "Overnight in BCI:\n1) Brain implant maker files to go public\n2) 脑机接口新进展"
