"""One pass of the Wire: poll whatever is due, alert on what's new, send digests on schedule.

Called every minute (EventBridge on AWS, or `python -m wire run` locally). Each source keeps
its own schedule, so a minute usually polls one or two feeds.
"""

from __future__ import annotations

import datetime as dt
import functools
import logging
import re
import time
import uuid

from census.post import _fit

from . import context as context_mod
from . import drafts, notify, tz
from .httpclient import OutOfTime
from .items import DIGEST, NORMAL, SILENT, URGENT, Item, key_hash
from .sources import PollEnv, all_sources

log = logging.getLogger(__name__)

FAIL_ALERT_AFTER = 5  # consecutive failures before a "source is failing" alert
SEEN_CAP = 1500  # remembered item ids per source (stored as short hashes)
DIGEST_CAP = 150
JITTER = dt.timedelta(seconds=20)  # schedules fire a little early or late
CJK = re.compile(r"[\u3400-\u9fff]")


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _parse(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


@functools.lru_cache(maxsize=8)
def local_zone(name: str) -> dt.tzinfo:
    return tz.zone(name)


def is_quiet(settings, now: dt.datetime) -> bool:
    if not settings.quiet:
        return False
    start, end = settings.quiet
    hour = now.astimezone(local_zone(settings.timezone)).hour
    if start == end:
        return False
    return (hour >= start or hour < end) if start > end else (start <= hour < end)


class Runner:
    def __init__(self, settings, state, session, notifier, sources=None):
        self.settings, self.state, self.session, self.notifier = settings, state, session, notifier
        self.sources = sources if sources is not None else all_sources(settings)
        self.report: dict = {}

    # ------------------------------------------------------------------ run
    def run(self, now: dt.datetime | None = None, force: bool = False, only: set[str] | None = None) -> dict:
        now = now or dt.datetime.now(dt.timezone.utc)
        owner = uuid.uuid4().hex
        if not self.state.acquire_lock(owner, 170):
            return {"skipped": "another run is in progress"}
        self.report = {"at": _iso(now), "polled": [], "sent": 0, "queued": 0, "errors": {}, "deferred": []}
        started = time.monotonic()
        try:
            ctx = context_mod.load(self.session, self.settings.site_url)
            seeded = []
            for source in self.sources:
                if source.name in self.settings.disabled or (only and source.name not in only):
                    continue
                key = f"src#{source.name}"
                meta = self.state.get(key) or {}
                last = _parse(meta.get("last_run", ""))
                if not force and last and now - last < dt.timedelta(minutes=source.every) - JITTER:
                    continue
                if time.monotonic() - started > self.settings.time_budget_s:
                    self.report["deferred"].append(source.name)
                    continue
                count = self._poll(source, meta, ctx, now)
                if count is not None:
                    seeded.append((source, count))
            if seeded:
                self._announce(seeded)
            self._maybe_digest(now)
        finally:
            self.state.release_lock(owner)
        self.report["seconds"] = round(time.monotonic() - started, 2)
        return self.report

    def _poll(self, source, meta: dict, ctx, now: dt.datetime) -> int | None:
        """Poll one source. Returns the item count when this was its first (seeding) run."""
        key = f"src#{source.name}"
        if source.needs_sec and not self.settings.sec_user_agent:
            if not meta.get("warned_sec"):
                self._route(Item(source="wire", key=f"health:{source.name}:sec", kind="health", priority=NORMAL,
                                 title=f"{source.name} is off until SEC_USER_AGENT is set",
                                 summary="SEC requires a contact email in the User-Agent. Set SEC_USER_AGENT to "
                                         "'BCI Census you@example.com' and redeploy."), ctx, now)
                meta["warned_sec"] = True
            meta["last_run"] = _iso(now)
            self.state.put(key, meta)
            return None

        seen_list = meta.get("seen") or []
        seen = set(seen_list)
        first = not meta.get("initialized")
        env = PollEnv(self.session, ctx, self.settings, self.state, now, seen=seen, bootstrap=first)
        try:
            items = source.poll(env)
        except OutOfTime:
            self.report["deferred"].append(source.name)  # not a failure: it runs again next minute
            return None
        except Exception as exc:
            meta["fail_count"] = meta.get("fail_count", 0) + 1
            meta["last_error"] = f"{type(exc).__name__}: {exc}"[:400]
            meta["last_run"] = _iso(now)
            self.report["errors"][source.name] = meta["last_error"]
            log.warning("%s failed (%s in a row): %s", source.name, meta["fail_count"], meta["last_error"])
            if meta["fail_count"] == FAIL_ALERT_AFTER:
                self._route(Item(source="wire", key=f"health:{source.name}:{now.date()}", kind="health",
                                 priority=NORMAL, title=f"{source.name} has failed {FAIL_ALERT_AFTER} times in a row",
                                 summary=f"Last error: {meta['last_error']}"), ctx, now)
            self.state.put(key, meta)
            return None

        fresh, batch = [], set()
        for item in items:
            h = key_hash(item.key)
            if h not in seen and h not in batch:  # also drops repeats within one poll
                batch.add(h)
                fresh.append((h, item))
        if not first:
            for _, item in fresh:
                self._route(item, ctx, now)
        new_hashes = [h for h, _ in fresh]
        meta.update(
            seen=(new_hashes + seen_list)[:SEEN_CAP],
            initialized=True,
            last_run=_iso(now),
            last_ok=_iso(now),
            fail_count=0,
            last_error="",
            warnings=env.warnings[:5],
        )
        self.state.put(key, meta)
        self.report["polled"].append({"source": source.name, "items": len(items), "new": len(fresh),
                                      "seeded": first})
        return len(items) if first else None

    # ---------------------------------------------------------------- route
    def _route(self, item: Item, ctx, now: dt.datetime) -> None:
        if item.priority <= SILENT:
            return
        card = ctx.card(item.program) if item.kind != "health" else ""
        if not item.draft and item.kind != "health":
            item.draft = drafts.draft(item, card)
        quiet = is_quiet(self.settings, now)
        hold = item.priority <= DIGEST or (quiet and not (self.settings.quiet_urgent and item.priority >= URGENT))
        if not hold:
            try:
                self.notifier.send(notify.for_item(item, card))
                self.report["sent"] += 1
                return
            except Exception as exc:  # the push service is down: keep it for the digest
                log.warning("Push failed, queueing for the digest: %s", exc)
        self._queue(item)

    def _queue(self, item: Item) -> None:
        record = self.state.get("digest") or {}
        queue = record.get("items") or []
        queue.append(item.to_dict())
        self.state.put("digest", {"items": queue[-DIGEST_CAP:]})
        self.report["queued"] += 1

    # --------------------------------------------------------------- digest
    def _maybe_digest(self, now: dt.datetime) -> None:
        if not self.settings.digest_hours or is_quiet(self.settings, now):
            return  # a slot missed during quiet hours rolls into the morning digest
        zone = local_zone(self.settings.timezone)
        local = now.astimezone(zone)
        meta = self.state.get("digest_meta") or {}
        last = _parse(meta.get("last_sent", ""))
        if last is None:  # start the clock on the first run
            self.state.put("digest_meta", {"last_sent": _iso(now)})
            return
        slots = []
        for days_back in (0, 1):
            day = local - dt.timedelta(days=days_back)
            for hour in self.settings.digest_hours:
                slots.append(day.replace(hour=hour, minute=0, second=0, microsecond=0))
        due = [s for s in slots if s <= local]
        if not due or last.astimezone(zone) >= max(due):
            return
        slot = max(due)
        queue = (self.state.get("digest") or {}).get("items") or []
        if queue:
            items = sorted((Item.from_dict(d) for d in queue), key=lambda i: i.published, reverse=True)
            items.sort(key=lambda i: -i.priority)  # stable: loudest first, newest first within a level
            label = "morning digest" if slot.hour < 12 else "evening digest"
            draft = self.digest_draft(items, slot.hour < 12)
            self.notifier.send(notify.digest(items, label, draft))  # raises: retried next minute
            self.state.put("digest", {"items": []})
            self.report["digest"] = len(items)
        self.state.put("digest_meta", {"last_sent": _iso(now)})

    @staticmethod
    def digest_draft(items: list[Item], morning: bool) -> str:
        picks = [i for i in items if i.kind not in ("health", "job")]
        # Chinese headlines stay in the digest list but go last in the English draft
        picks = sorted(picks, key=lambda i: bool(CJK.search(i.extra.get("headline") or i.title)))[:3]
        if not picks:
            return ""
        lead = "Overnight in BCI:" if morning else "Today in BCI:"
        lines = [lead]
        for n, item in enumerate(picks, 1):
            headline = item.extra.get("headline") or item.title
            lines.append(f"{n}) {headline}")
        return _fit("\n".join(lines))

    # ------------------------------------------------------------- announce
    def _announce(self, seeded: list) -> None:
        lines = [f"- {s.name} (every {s.every} min): {n} current items recorded" for s, n in seeded]
        note = notify.Notification(
            title=f"BCI Wire is watching {len(seeded)} new source{'s' if len(seeded) != 1 else ''}",
            message="Existing items were recorded without alerts. You'll hear about anything new.\n\n" + "\n".join(lines),
            priority=3,
            tags=["wire"],
        )
        try:
            self.notifier.send(note)
        except Exception as exc:
            log.warning("Could not send the startup notice: %s", exc)
