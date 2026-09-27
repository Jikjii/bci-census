"""Keyword signals the watchers use to decide what's relevant and how loud to be."""

from __future__ import annotations

import re

from census.scope import BCI_SIGNALS

_I = re.IGNORECASE

# Headlines and paper titles: broader than the trial classifier, because press says "brain chip".
EXTRA_NEWS = [
    re.compile(p, _I)
    for p in (
        r"brain[\s-]*(?:implant|chip)s?",
        r"neural implant",
        r"neuroprosthe\w*",
        r"neurotech\w*",
        r"brain[\s-]*(?:computer|machine)?[\s-]*interface",
        r"(?:thought|mind)[\s-]*controlled",
        r"thoughts? (?:into|to) (?:speech|text|words)",
        r"intracortical",
        r"electrocorticograph\w*",
    )
]


def relevant(text: str, aliases: list[str] | None = None) -> bool:
    if not text:
        return False
    if any(p.search(text) for p in BCI_SIGNALS) or any(p.search(text) for p in EXTRA_NEWS):
        return True
    low = " " + text.lower() + " "
    for alias in aliases or []:
        a = alias.lower()
        if len(a) >= 5 and re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z])", low):
            return True
    return False


# Primary sources for company news: a release here is the company talking.
PRESS_WIRES = ("globenewswire.com", "prnewswire.com", "businesswire.com", "accessnewswire.com", "accesswire.com")

# Outlets whose BCI stories are worth a push even when the company didn't issue a release.
TIER_ONE = (
    "reuters.com", "bloomberg.com", "statnews.com", "wsj.com", "ft.com", "nytimes.com", "apnews.com",
    "cnbc.com", "technologyreview.com", "wired.com", "theverge.com", "techcrunch.com", "nature.com",
    "science.org", "axios.com", "fiercebiotech.com", "medtechdive.com", "endpts.com", "washingtonpost.com",
    "theinformation.com", "semafor.com", "scmp.com", "caixinglobal.com", "xinhuanet.com", "chinadaily.com.cn",
)


def domain_in(url: str, domains: tuple[str, ...]) -> bool:
    host = re.sub(r"^https?://", "", (url or "").lower()).split("/")[0]
    return any(host == d or host.endswith("." + d) for d in domains)


# Chinese headlines that usually mean news, not commentary: approvals, registrations, firsts, money, pricing.
CN_EVENT = re.compile(r"获批|批准|注册证|首例|首个|融资|亿元|临床试验|入组|植入|医保|定价|收费|上市")

# Job titles that tend to signal a new trial site, market or regulatory push.
JOB_SIGNAL = re.compile(r"clinical|regulatory|reimbursement|market access|medical affairs|patient|country manager|"
                        r"site|surgeon|neurosurg|commercial", _I)
