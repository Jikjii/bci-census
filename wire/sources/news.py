"""News through Google News RSS: press releases (the company speaking), major outlets, and a
Chinese-language feed for approvals and financings that break overnight US time."""

from __future__ import annotations

import os
import re

from ..feeds import parse_feed
from ..items import DIGEST, HIGH, URGENT, Item
from ..signals import CN_EVENT, PRESS_WIRES, TIER_ONE, domain_in, relevant
from . import Source

GOOGLE_NEWS = "https://news.google.com/rss/search"

ENGLISH_QUERY = (
    '"brain-computer interface" OR "brain computer interface" OR "brain implant" OR "brain chip" OR '
    'Neuralink OR Synchron OR Paradromics OR "Precision Neuroscience" OR "Blackrock Neurotech" OR Neuracle OR '
    'NeuCyber OR "Onward Medical" OR BrainGate OR Axoft OR StairMed when:2d'
)
CHINESE_QUERY = "脑机接口 when:2d"


class GoogleNews(Source):
    def __init__(self, name: str, query: str, hl: str, gl: str, ceid: str, every: int, lang: str, description: str):
        self.name, self.query, self.hl, self.gl, self.ceid = name, query, hl, gl, ceid
        self.every, self.lang, self.description = every, lang, description

    @classmethod
    def english(cls) -> "GoogleNews":
        return cls("news_en", os.environ.get("WIRE_NEWS_QUERY", ENGLISH_QUERY), "en-US", "US", "US:en", 3, "en",
                   "Press releases and major outlets (Google News)")

    @classmethod
    def chinese(cls) -> "GoogleNews":
        return cls("news_zh", os.environ.get("WIRE_NEWS_QUERY_ZH", CHINESE_QUERY), "zh-CN", "CN", "CN:zh-Hans", 5, "zh",
                   "Chinese-language BCI news: approvals, financings, first cases")

    def poll(self, env) -> list[Item]:
        resp = env.session.get(GOOGLE_NEWS, params={"q": self.query, "hl": self.hl, "gl": self.gl, "ceid": self.ceid})
        resp.raise_for_status()
        aliases = env.ctx.aliases()
        items = []
        for entry in parse_feed(resp.content):
            outlet = entry.source_name
            headline = entry.title
            if outlet and headline.endswith(f" - {outlet}"):
                headline = headline[: -len(outlet) - 3].strip()
            if self.lang == "en" and not relevant(headline, aliases):
                continue  # the story mentions BCI somewhere, but the headline isn't about it
            pid = env.ctx.program_for_text(headline)
            if self.lang == "zh":
                kind, priority = "news_cn", (HIGH if CN_EVENT.search(headline) else DIGEST)
            elif domain_in(entry.source_url, PRESS_WIRES):
                kind, priority = "press", (URGENT if pid else HIGH)
            elif domain_in(entry.source_url, TIER_ONE):
                kind, priority = "news", HIGH
            else:
                kind, priority = "news", DIGEST
            items.append(
                Item(
                    source=self.name,
                    key=entry.id or entry.link,
                    kind=kind,
                    title=f"{headline} ({outlet})" if outlet else headline,
                    url=entry.link,
                    published=entry.published,
                    program=pid,
                    priority=priority,
                    lang=self.lang,
                    summary=f"{outlet or 'Unknown outlet'}, {entry.published[:16].replace('T', ' ')} UTC",
                    extra={"headline": re.sub(r"\s+", " ", headline), "outlet": outlet},
                )
            )
        return items
