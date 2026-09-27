"""Source watchers. Each one polls a primary source and returns Items; the runner handles
scheduling, first-run seeding, de-duplication, routing and failures."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class PollEnv:
    session: object
    ctx: object
    settings: object
    state: object
    now: dt.datetime
    seen: set = field(default_factory=set)
    bootstrap: bool = False
    warnings: list = field(default_factory=list)

    def has_seen(self, key: str) -> bool:
        from ..items import key_hash

        return key_hash(key) in self.seen


class Source:
    name = ""
    every = 60  # minutes between polls
    needs_sec = False  # SEC hosts need SEC_USER_AGENT with a contact email
    description = ""

    def poll(self, env: PollEnv) -> list:
        raise NotImplementedError


def all_sources(settings) -> list[Source]:
    from .edgar import EdgarCompanies, EdgarFullText
    from .fda import FdaPress, OpenFdaDecisions
    from .fedreg import FederalRegister
    from .jobs import JobBoards
    from .journals import Journals
    from .news import GoogleNews
    from .preprints import Preprints
    from .pubmed import PubMed
    from .trials import ClinicalTrials

    return [
        EdgarCompanies(),
        GoogleNews.english(),
        EdgarFullText(),
        GoogleNews.chinese(),
        Journals(),
        FdaPress(),
        ClinicalTrials(),
        FederalRegister(),
        PubMed(),
        Preprints(),
        JobBoards(settings.job_boards),
        OpenFdaDecisions(),
    ]
