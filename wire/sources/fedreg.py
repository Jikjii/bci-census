"""Federal Register: rules, notices and guidance that mention BCIs (CMS payment, FDA guidance)."""

from __future__ import annotations

from ..items import URGENT, Item
from . import Source

API = "https://www.federalregister.gov/api/v1/documents.json"
TERMS = ('"brain-computer interface"', '"brain computer interface"', '"implanted brain"')


class FederalRegister(Source):
    name = "fedreg"
    every = 120
    description = "Federal Register documents that mention BCIs"

    def poll(self, env) -> list[Item]:
        found: dict[str, Item] = {}
        for term in TERMS:
            resp = env.session.get(API, params={"conditions[term]": term, "order": "newest", "per_page": 20})
            resp.raise_for_status()
            for doc in resp.json().get("results") or []:
                number = doc.get("document_number")
                if not number or number in found:
                    continue
                agencies = ", ".join(a.get("name", "") for a in doc.get("agencies") or [] if a.get("name")) or "Federal Register"
                found[number] = Item(
                    source=self.name,
                    key=number,
                    kind="fedreg",
                    title=f"{agencies}: {doc.get('title', '')}",
                    url=doc.get("html_url", ""),
                    published=doc.get("publication_date", ""),
                    priority=URGENT,
                    summary=f"{doc.get('type', 'Document')} published {doc.get('publication_date', '')}. "
                            f"{(doc.get('abstract') or '')[:300]}",
                    extra={"agency": agencies, "headline": doc.get("title", "")},
                )
        return list(found.values())
