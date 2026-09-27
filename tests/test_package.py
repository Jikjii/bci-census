"""The Lambda package: standard library only, and the DynamoDB state against a real DynamoDB model."""

import datetime as dt
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_wire_imports_nothing_outside_the_standard_library():
    code = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
import wire.lambda_handler, wire.__main__
from wire.config import Settings
from wire.sources import all_sources
all_sources(Settings())
extra = sorted({{m.split('.')[0] for m in sys.modules}} - set(sys.stdlib_module_names) - {{'wire', 'census', '__main__'}})
print(','.join(extra))
"""
    # -S skips site-packages, so an import of requests, yaml or boto3 at module level fails here
    out = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""


@pytest.fixture
def table(monkeypatch):
    moto = pytest.importorskip("moto")  # optional: pip install "moto[dynamodb]" boto3
    import boto3

    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with moto.mock_aws():
        db = boto3.resource("dynamodb")
        t = db.create_table(TableName="bci-wire-state", BillingMode="PAY_PER_REQUEST",
                            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
                            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}])
        yield t


def test_dynamo_lock_with_real_condition_expressions(table, monkeypatch):
    from wire.state import DynamoState

    state = DynamoState("bci-wire-state")
    state.put("src#news_en", {"seen": ["ab" * 8], "last_run": "2026-09-26T16:00:00+00:00"})
    assert state.get("src#news_en")["seen"] == ["ab" * 8] and state.get("missing") is None
    state.put("digest", {"items": [{"title": "Brain–computer interface, 脑机接口"}]}, ttl_days=2)
    assert state.get("digest")["items"][0]["title"] == "Brain–computer interface, 脑机接口"
    assert int(table.get_item(Key={"pk": "digest"})["Item"]["expires_at"]) > time.time() + 86400

    assert state.acquire_lock("run-1", 170) is True
    assert state.acquire_lock("run-2", 170) is False
    state.release_lock("run-2")  # not the owner: the lock stays
    assert state.acquire_lock("run-3", 170) is False
    state.release_lock("run-1")
    assert state.acquire_lock("run-2", 170) is True

    later = time.time() + 200  # a crashed run's lock expires on its own
    monkeypatch.setattr(time, "time", lambda: later)
    assert state.acquire_lock("run-4", 170) is True


def test_runner_on_dynamodb(table, monkeypatch, tmp_path):
    from test_wire import DAY, FakeWeb  # the fixture web from the main Wire tests
    from wire import runner as runner_mod
    from wire.config import Settings
    from wire.context import Context
    from wire.notify import PrintNotifier
    from wire.state import DynamoState

    ctx = Context({"programs": []}, {"programs": [{"id": "neuralink", "name": "Neuralink", "aliases": ["neuralink"],
                                                   "cik": 1708503}]})
    monkeypatch.setattr(runner_mod.context_mod, "load", lambda session, site_url: ctx)
    settings = Settings(sec_user_agent="BCI Census test@example.com", table="bci-wire-state")
    notifier = PrintNotifier(echo=False)
    runner = runner_mod.Runner(settings, DynamoState("bci-wire-state"), FakeWeb(), notifier)
    first = runner.run(now=DAY, force=True)
    assert not first["errors"] and len(first["polled"]) == 12
    second = runner.run(now=DAY + dt.timedelta(minutes=1))
    assert [p["source"] for p in second["polled"]] == ["edgar_companies"]
    assert table.get_item(Key={"pk": "lock"}).get("Item") is None  # released after each run
