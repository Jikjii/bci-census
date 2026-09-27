"""The unit the Wire passes around: one thing that happened, with its source and a draft post."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

# Priority: 5 = ring now (money, approvals, new trials), 4 = push, 3 = quiet push, 2 = digest only,
# 0 = record as seen without telling anyone (a board or feed being seeded).
URGENT, HIGH, NORMAL, DIGEST, SILENT = 5, 4, 3, 2, 0

KIND_LABEL = {
    "form_d": "Form D",
    "sec_filing": "SEC filing",
    "sec_mention": "SEC mention",
    "trial_new": "New trial",
    "trial_status": "Trial status",
    "trial_enrollment": "Trial enrollment",
    "trial_scope": "Trial now in scope",
    "press": "Press release",
    "news": "News",
    "news_cn": "China",
    "paper": "Paper",
    "preprint": "Preprint",
    "fda": "FDA",
    "fda_decision": "FDA decision",
    "fedreg": "Federal Register",
    "job": "Hiring",
    "health": "Wire health",
}


@dataclass
class Item:
    source: str
    key: str
    kind: str
    title: str
    url: str = ""
    published: str = ""
    program: str = ""
    summary: str = ""
    draft: str = ""
    priority: int = NORMAL
    lang: str = "en"
    extra: dict = field(default_factory=dict)  # facts the draft template needs (amounts, sponsor, ...)

    @property
    def label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        fields = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**fields)


def key_hash(key: str) -> str:
    """Short, fixed-size id for the seen list (feed ids can be 100+ characters)."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
