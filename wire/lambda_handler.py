"""AWS Lambda entry point. EventBridge invokes it every minute; the runner decides what's due.

Manual invocations (Lambda console "Test", or `aws lambda invoke`):
    {"test": true}     send one test alert to your phone
    {"status": true}   what each source did last
    {"force": true}    poll every source now; add "only": ["news_en"] to pick sources
"""

from __future__ import annotations

import json
import logging
import time

from .config import Settings
from .httpclient import Session
from .notify import Notification, PrintNotifier, build_notifier
from .runner import Runner
from .sources import all_sources
from .state import open_state

logging.getLogger().setLevel(logging.INFO)


RESERVE_S = 10  # kept back at the end of a run to save state and release the lock


def handler(event, context=None):
    event = event if isinstance(event, dict) else {}
    settings = Settings.from_env()
    session = Session(settings.user_agent, settings.sec_user_agent)
    if context is not None and hasattr(context, "get_remaining_time_in_millis"):
        left = context.get_remaining_time_in_millis() / 1000
        session.deadline = time.monotonic() + left - RESERVE_S  # no request outlives the function
        settings.time_budget_s = min(settings.time_budget_s, max(5.0, left - 30))  # no new source after this
    notifier = build_notifier(settings, session)

    if event.get("test"):
        notifier.send(Notification(title="BCI Wire test", priority=4, tags=["wire"],
                                   message="If this reached your phone, alerts will too.",
                                   actions=[("Draft post", "https://twitter.com/intent/tweet?text=Testing%20the%20BCI%20Wire")]))
        channel = "printed only: no alert channel is set" if isinstance(notifier, PrintNotifier) else type(notifier).__name__
        return {"test": "sent", "channel": channel}

    state = open_state(settings)
    if event.get("status"):
        report = {}
        for source in all_sources(settings):
            meta = state.get(f"src#{source.name}") or {}
            report[source.name] = {k: meta.get(k) for k in ("last_run", "last_ok", "fail_count", "last_error")}
        report["digest_queue"] = len((state.get("digest") or {}).get("items") or [])
        return report

    only = set(event.get("only") or [])
    report = Runner(settings, state, session, notifier).run(force=bool(event.get("force")), only=only or None)
    print(json.dumps(report))  # one line per run in CloudWatch Logs
    return report
