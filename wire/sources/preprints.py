"""bioRxiv and medRxiv: new BCI preprints, collected for the digest."""

from __future__ import annotations

import datetime as dt

from census.scope import BCI_SIGNALS

from ..items import DIGEST, Item
from . import Source

API = "https://api.biorxiv.org/details/{server}/{start}/{end}/{cursor}/json"
VENUE = {"biorxiv": "bioRxiv", "medrxiv": "medRxiv"}
MAX_PAGES = 12


class Preprints(Source):
    name = "preprints"
    every = 240
    description = "bioRxiv and medRxiv BCI preprints (digest)"

    def poll(self, env) -> list[Item]:
        end = env.now.date()
        start = end - dt.timedelta(days=1)
        items = []
        for server in ("biorxiv", "medrxiv"):
            cursor = 0
            for _ in range(MAX_PAGES):
                resp = env.session.get(API.format(server=server, start=start.isoformat(), end=end.isoformat(),
                                                  cursor=cursor), timeout=30)
                resp.raise_for_status()
                payload = resp.json()
                batch = payload.get("collection") or []
                for paper in batch:
                    text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
                    if not any(p.search(text) for p in BCI_SIGNALS):
                        continue
                    doi = paper.get("doi", "")
                    items.append(
                        Item(
                            source=self.name,
                            key=f"{doi}v{paper.get('version', '1')}",
                            kind="preprint",
                            title=f"{VENUE[server]}: {paper.get('title', '')}",
                            url=f"https://doi.org/{doi}" if doi else "",
                            published=paper.get("date", ""),
                            program=env.ctx.program_for_text(text),
                            priority=DIGEST,
                            summary=f"{VENUE[server]} ({paper.get('category', '')}), {paper.get('date', '')}",
                            extra={"venue": VENUE[server], "headline": paper.get("title", "")},
                        )
                    )
                messages = (payload.get("messages") or [{}])[0]
                total = int(messages.get("total") or 0)
                cursor += len(batch)
                if not batch or cursor >= total:
                    break
        return items
