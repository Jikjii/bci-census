"""PubMed: new papers on implanted BCIs, collected for the digest."""

from __future__ import annotations

from ..items import DIGEST, Item
from . import Source

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
TERM = (
    '("brain-computer interface"[tiab] OR "brain-machine interface"[tiab] OR "speech neuroprosthesis"[tiab] '
    'OR intracortical[tiab] OR electrocorticography[tiab]) AND (implant*[tiab] OR intracortical[tiab] '
    'OR electrocorticograph*[tiab] OR "microelectrode array"[tiab] OR endovascular[tiab])'
)


class PubMed(Source):
    name = "pubmed"
    every = 120
    description = "PubMed papers on implanted BCIs (digest)"

    def poll(self, env) -> list[Item]:
        resp = env.session.get(ESEARCH, params={"db": "pubmed", "term": TERM, "reldate": 3, "datetype": "edat",
                                                "retmode": "json", "retmax": 100, "tool": "bci-census-wire"})
        resp.raise_for_status()
        ids = (resp.json().get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return []
        resp = env.session.get(ESUMMARY, params={"db": "pubmed", "id": ",".join(ids), "retmode": "json",
                                                 "tool": "bci-census-wire"})
        resp.raise_for_status()
        result = resp.json().get("result") or {}
        items = []
        for uid in result.get("uids") or []:
            rec = result.get(uid) or {}
            journal = rec.get("fulljournalname") or rec.get("source") or "PubMed"
            title = (rec.get("title") or "").rstrip(".")
            items.append(
                Item(
                    source=self.name,
                    key=uid,
                    kind="paper",
                    title=f"{journal}: {title}",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
                    published=rec.get("sortpubdate", "")[:10].replace("/", "-"),
                    program=env.ctx.program_for_text(title),
                    priority=DIGEST,
                    summary=f"{journal}, {rec.get('pubdate', '')}",
                    extra={"venue": journal, "headline": title},
                )
            )
        return items
