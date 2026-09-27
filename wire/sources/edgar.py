"""SEC EDGAR: every filing by a tracked company (minute by minute), plus any company whose new
filing mentions brain-computer interfaces (public companies pivoting into BCI show up here)."""

from __future__ import annotations

import datetime as dt
import re

from census.sources.edgar import parse_form_d

from ..drafts import a_form, money
from ..feeds import parse_feed
from ..items import HIGH, URGENT, Item
from . import Source

COMPANY_FEED = "https://www.sec.gov/cgi-bin/browse-edgar"
FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"
FULL_TEXT_QUERIES = ('"brain-computer interface"', '"brain-machine interface"')
FORM_D = ("D", "D/A")


class EdgarCompanies(Source):
    name = "edgar_companies"
    every = 1
    needs_sec = True
    description = "Every SEC filing by tracked companies (Form D = money raised)"

    def poll(self, env) -> list[Item]:
        items = []
        for program in env.ctx.programs:
            if not program.get("cik"):
                continue
            cik = str(int(program["cik"])).zfill(10)
            resp = env.session.get(COMPANY_FEED, params={"action": "getcompany", "CIK": cik, "type": "", "dateb": "",
                                                         "owner": "include", "count": 20, "output": "atom"})
            resp.raise_for_status()
            company = env.ctx.name(program["id"])
            for entry in parse_feed(resp.content):
                fields = entry.extra
                accession = fields.get("accession-number") or entry.id.rsplit("=", 1)[-1]
                form = fields.get("filing-type") or (entry.categories[0] if entry.categories else "")
                filed = fields.get("filing-date") or entry.published[:10]
                href = fields.get("filing-href") or entry.link
                is_d = form in FORM_D
                item = Item(
                    source=self.name,
                    key=accession,
                    kind="form_d" if is_d else "sec_filing",
                    title=f"{company} filed Form {form} ({filed})",
                    url=href,
                    published=entry.published,
                    program=program["id"],
                    priority=URGENT if is_d else HIGH,
                    summary=f"{company}: {fields.get('form-name') or 'Form ' + form}, filed {filed}.",
                    extra={"company": company, "form": form, "filing_date": filed},
                )
                if is_d and not env.has_seen(accession) and not env.bootstrap:
                    self._read_amounts(env, item, href)
                items.append(item)
        return items

    @staticmethod
    def _read_amounts(env, item: Item, href: str) -> None:
        folder = href.rsplit("/", 1)[0]
        try:
            doc = env.session.get(folder + "/primary_doc.xml")
            doc.raise_for_status()
            facts = parse_form_d(doc.text)
        except Exception as exc:  # the alert still goes out without amounts
            env.warnings.append(f"Form D amounts unreadable for {item.key}: {exc}")
            return
        keep = ("total_amount_sold", "total_offering_amount", "investors_count", "date_of_first_sale", "is_amendment")
        item.extra.update({k: facts.get(k) for k in keep})
        sold = money(facts.get("total_amount_sold")) or "amount not stated"
        offered = money(facts.get("total_offering_amount"))
        item.summary = (
            f"{item.extra['company']} Form {item.extra['form']}: {sold} sold"
            + (f" of {offered} offered" if offered and offered != sold else "")
            + f"; first sale {facts.get('date_of_first_sale') or 'not stated'}"
            + (f"; {facts['investors_count']} investors" if facts.get("investors_count") else "")
            + "."
        )


class EdgarFullText(Source):
    name = "edgar_fulltext"
    every = 5
    needs_sec = True
    description = "Any new SEC filing that mentions brain-computer interfaces"

    def poll(self, env) -> list[Item]:
        end = env.now.date()
        start = end - dt.timedelta(days=3)
        found: dict[str, Item] = {}
        for query in FULL_TEXT_QUERIES:
            resp = env.session.get(FULL_TEXT, params={"q": query, "dateRange": "custom",
                                                      "startdt": start.isoformat(), "enddt": end.isoformat()})
            resp.raise_for_status()
            for hit in (resp.json().get("hits") or {}).get("hits") or []:
                src = hit.get("_source") or {}
                hit_id = hit.get("_id", "")
                accession = src.get("adsh") or hit_id.split(":")[0]
                ciks = src.get("ciks") or []
                if not accession or accession in found or not ciks:
                    continue
                if env.ctx.program_for_cik(ciks[0]):
                    continue  # tracked companies are covered filing by filing
                names = src.get("display_names") or ["Unknown filer"]
                company = " ".join(re.sub(r"\s*\(CIK[^)]*\)", "", names[0]).split())
                form = src.get("form") or src.get("file_type") or "filing"
                filed = src.get("file_date", "")
                folder = f"https://www.sec.gov/Archives/edgar/data/{int(ciks[0])}/{accession.replace('-', '')}"
                filename = hit_id.split(":", 1)[1] if ":" in hit_id else ""
                found[accession] = Item(
                    source=self.name,
                    key=accession,
                    kind="sec_mention",
                    title=f"{company}: {form} mentions brain-computer interfaces",
                    url=f"{folder}/{filename}" if filename else f"{folder}/{accession}-index.htm",
                    published=filed,
                    priority=HIGH,
                    summary=f"{company} filed {a_form(form)} on {filed} that mentions brain-computer interfaces. "
                            f"Filing index: {folder}/{accession}-index.htm",
                    extra={"company": company, "form": form, "filing_date": filed},
                )
        return list(found.values())
