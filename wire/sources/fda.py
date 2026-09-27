"""FDA: press releases that mention BCIs, and 510(k)/PMA decisions for tracked companies."""

from __future__ import annotations

from census import config as census_config
from census.link import link_fda
from census.sources.openfda import fetch_decisions

from ..items import URGENT, Item
from . import Source
from .journals import KeywordFeeds

FDA_PRESS = "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml"


class FdaPress(KeywordFeeds):
    name = "fda_press"
    every = 15
    kind = "fda"
    description = "FDA press releases that mention BCIs or tracked companies"
    feeds = [("FDA", FDA_PRESS, URGENT)]


class OpenFdaDecisions(Source):
    name = "openfda"
    every = 720
    description = "510(k) and PMA decisions for tracked companies (openFDA updates weekly)"

    def poll(self, env) -> list[Item]:
        applicants = sorted({a for p in env.ctx.programs for a in (p.get("fda_applicants") or [])})
        decisions = fetch_decisions(env.session, applicants, census_config.FDA_DEVICE_KEYWORDS,
                                    env.settings.openfda_api_key)
        items = []
        for d in decisions:
            pid = link_fda(d, env.ctx.programs)
            if not pid:
                continue
            items.append(
                Item(
                    source=self.name,
                    key=d["id"],
                    kind="fda_decision",
                    title=f"{d['kind']} {d['id']}: {d['device_name']} ({d['applicant']})",
                    url=d["url"],
                    published=d["decision_date"],
                    program=pid,
                    priority=URGENT,
                    summary=f"{d['applicant']}: {d['kind']} {d['id']} for {d['device_name']}, decided "
                            f"{d['decision_date']} ({d['decision']}).",
                    extra=dict(d),
                )
            )
        return items
