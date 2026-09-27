"""Company job boards. A posting in a city or country the company has never hired in is often
the first public sign of a new trial site or market, weeks before a press release."""

from __future__ import annotations

from ..items import DIGEST, HIGH, NORMAL, SILENT, Item
from ..signals import JOB_SIGNAL
from . import Source

# Confirmed live on 2026-09-26. Add others with WIRE_JOB_BOARDS (see README): the provider and
# slug are in the company's careers-page URL, e.g. jobs.lever.co/<slug> or jobs.ashbyhq.com/<slug>.
DEFAULT_BOARDS = [{"program": "neuralink", "provider": "greenhouse", "slug": "neuralink"}]
LOCATIONS_KEY = "job_locations"


def _fetch(session, provider: str, slug: str) -> list[dict]:
    if provider == "greenhouse":
        resp = session.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        resp.raise_for_status()
        return [{"id": str(j["id"]), "title": j.get("title", ""), "location": (j.get("location") or {}).get("name", ""),
                 "url": j.get("absolute_url", ""), "published": j.get("first_published") or j.get("updated_at", "")}
                for j in resp.json().get("jobs") or []]
    if provider == "lever":
        resp = session.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
        resp.raise_for_status()
        return [{"id": j["id"], "title": j.get("text", ""), "location": (j.get("categories") or {}).get("location", ""),
                 "url": j.get("hostedUrl", ""), "published": ""} for j in resp.json()]
    if provider == "ashby":
        resp = session.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        resp.raise_for_status()
        return [{"id": j["id"], "title": j.get("title", ""), "location": j.get("location", ""),
                 "url": j.get("jobUrl", ""), "published": j.get("publishedAt", "")} for j in resp.json().get("jobs") or []]
    raise ValueError(f"unknown job board provider {provider!r}")


def _places(location: str) -> list[str]:
    return [p.strip() for p in (location or "").split(";") if p.strip()]


class JobBoards(Source):
    name = "jobs"
    every = 360
    description = "Company job boards: new locations and clinical or regulatory roles"

    def __init__(self, extra_boards: list[dict] | None = None):
        self.boards = DEFAULT_BOARDS + list(extra_boards or [])

    def poll(self, env) -> list[Item]:
        known = (env.state.get(LOCATIONS_KEY) or {}).get("boards") or {}
        items = []
        for board in self.boards:
            board_key = f"{board['provider']}:{board['slug']}"
            company = env.ctx.name(board.get("program", "")) or board["slug"]
            places = set(known.get(board_key) or [])
            seeded = board_key in known
            for job in _fetch(env.session, board["provider"], board["slug"]):
                new_places = [p for p in _places(job["location"]) if p not in places]
                places.update(_places(job["location"]))
                if not seeded:
                    priority, note = SILENT, ""  # a board added later is seeded quietly, like the first run
                elif new_places:
                    priority, note = HIGH, f"New location for {company}: {', '.join(new_places)}."
                elif JOB_SIGNAL.search(job["title"]):
                    priority, note = NORMAL, "Clinical, regulatory or commercial role."
                else:
                    priority, note = DIGEST, ""
                items.append(
                    Item(
                        source=self.name,
                        key=f"{board_key}:{job['id']}",
                        kind="job",
                        title=f"{company}: {job['title']} ({job['location'] or 'location not listed'})",
                        url=job["url"],
                        published=job["published"],
                        program=board.get("program", ""),
                        priority=priority,
                        summary=note,
                        extra={"company": company, "job_title": job["title"], "location": job["location"]},
                    )
                )
            known[board_key] = sorted(places)
        env.state.put(LOCATIONS_KEY, {"boards": known})
        return items
