"""Small helpers shared across the package."""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Iterable

_PARTIAL_DATE = re.compile(r"^\d{4}(-\d{2}){0,2}$")


def norm_date(value: Any) -> str:
    """Return YYYY, YYYY-MM or YYYY-MM-DD from the formats the sources use."""
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if _PARTIAL_DATE.match(s):
        return s
    for fmt, out in (("%B %Y", "%Y-%m"), ("%B %d, %Y", "%Y-%m-%d"), ("%m/%d/%Y", "%Y-%m-%d")):
        try:
            return dt.datetime.strptime(s, fmt).strftime(out)
        except ValueError:
            continue
    return s


def date_key(value: Any) -> str:
    """Sortable key that places partial dates before full dates in the same period."""
    s = norm_date(value)
    if re.fullmatch(r"\d{4}", s):
        return s + "-00-00"
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s + "-00"
    return s


def norm_name(s: str) -> str:
    """Lowercase company name without punctuation or corporate suffixes."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(inc|incorporated|corp|corporation|co|llc|ltd|limited|holdings|plc|the)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def jsonable(obj: Any) -> Any:
    """Convert YAML-loaded dates (and nested structures) into JSON-safe values."""
    if isinstance(obj, (dt.date, dt.datetime)):
        return norm_date(obj)
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: Iterable[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {}
            for key in columns:
                val = jsonable(row.get(key, ""))
                flat[key] = "; ".join(map(str, val)) if isinstance(val, list) else val
            writer.writerow(flat)
