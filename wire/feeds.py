"""Parse RSS 2.0, RSS 1.0 (RDF, used by Nature) and Atom (used by SEC) into one shape."""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

_TAGS = re.compile(r"<[^>]+>")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(el: ET.Element, *names: str) -> ET.Element | None:
    for child in el:
        if _local(child.tag) in names:
            return child
    return None


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def clean(text: str) -> str:
    """Strip HTML tags and entities, collapse whitespace."""
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub(" ", text or ""))).strip()


def parse_date(value: str) -> str:
    """Return an ISO 8601 UTC timestamp, or '' when the date can't be read."""
    value = (value or "").strip()
    if not value:
        return ""
    parsed = None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if parsed is None:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class Entry:
    id: str
    title: str
    link: str
    published: str
    summary: str = ""
    source_name: str = ""
    source_url: str = ""
    categories: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def _link(el: ET.Element) -> str:
    fallback = ""
    for child in el:
        if _local(child.tag) != "link":
            continue
        href = child.get("href")
        if href:  # Atom
            if child.get("rel", "alternate") == "alternate":
                return href.strip()
            fallback = fallback or href.strip()
        elif _text(child):  # RSS
            return _text(child)
    return fallback


def parse_feed(data: bytes | str) -> list[Entry]:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    root = ET.fromstring(raw)
    entries = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        link = _link(el)
        ident = _text(_child(el, "guid", "id")) or el.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "") or link
        date = ""
        for name in ("pubDate", "published", "updated", "date", "issued"):
            date = parse_date(_text(_child(el, name)))
            if date:
                break
        source = _child(el, "source")
        extra = {}
        content = _child(el, "content")
        if content is not None and len(content):  # SEC's Atom puts filing fields inside <content>
            extra = {_local(c.tag): _text(c) for c in content}
        categories = [c.get("term") or _text(c) for c in el if _local(c.tag) == "category"]
        entries.append(
            Entry(
                id=ident,
                title=clean(_text(_child(el, "title"))),
                link=link,
                published=date,
                summary=clean(_text(_child(el, "description", "summary", "encoded"))),
                source_name=_text(source),
                source_url=(source.get("url", "") if source is not None else ""),
                categories=[c for c in categories if c],
                extra=extra,
            )
        )
    return entries
