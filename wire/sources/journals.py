"""Journal feeds, checked every ten minutes so a paper lands on your phone when the embargo lifts."""

from __future__ import annotations

import logging

from ..feeds import parse_feed
from ..items import HIGH, NORMAL, Item
from ..signals import relevant
from . import Source

log = logging.getLogger(__name__)

JOURNAL_FEEDS = [
    ("Nature", "https://www.nature.com/nature.rss", HIGH),
    ("Nature Medicine", "https://www.nature.com/nm.rss", HIGH),
    ("Nature Biomedical Engineering", "https://www.nature.com/natbiomedeng.rss", HIGH),
    ("Nature Neuroscience", "https://www.nature.com/neuro.rss", HIGH),
    ("Science", "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science", HIGH),
    ("NEJM", "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss", HIGH),
    ("Journal of Neural Engineering", "https://iopscience.iop.org/journal/rss/1741-2552", NORMAL),
]


class KeywordFeeds(Source):
    """Poll a list of RSS/Atom feeds and keep entries whose title or summary is about BCIs."""

    kind = "paper"
    feeds: list = []

    def poll(self, env) -> list[Item]:
        items, failures = [], []
        aliases = env.ctx.aliases()
        for venue, url, priority in self.feeds:
            try:
                resp = env.session.get(url, timeout=20)
                resp.raise_for_status()
                entries = parse_feed(resp.content)
            except Exception as exc:
                failures.append(f"{venue}: {exc}")
                continue
            for entry in entries:
                if not relevant(f"{entry.title} {entry.summary}", aliases):
                    continue
                items.append(
                    Item(
                        source=self.name,
                        key=entry.id or entry.link,
                        kind=self.kind,
                        title=f"{venue}: {entry.title}",
                        url=entry.link,
                        published=entry.published,
                        program=env.ctx.program_for_text(entry.title, entry.summary),
                        priority=priority,
                        summary=(entry.summary[:400] + "…") if len(entry.summary) > 400 else entry.summary,
                        extra={"venue": venue, "headline": entry.title, "agency": venue},
                    )
                )
        if failures and len(failures) == len(self.feeds):
            raise RuntimeError("; ".join(failures))
        env.warnings.extend(failures)
        return items


class Journals(KeywordFeeds):
    name = "journals"
    every = 10
    description = "Nature, Science, NEJM and field journals (embargo lifts)"
    feeds = JOURNAL_FEEDS
