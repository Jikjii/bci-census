"""Settings for the Wire, read from environment variables so the same code runs locally and on AWS."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Mapping

DEFAULT_USER_AGENT = "BCI-Census-Wire/0.1 (+https://github.com/jikjii/bci-census)"


def _quiet(value: str) -> tuple[int, int] | None:
    """'23-7' means quiet from 23:00 to 07:00 local time. 'off' disables quiet hours."""
    value = (value or "").strip().lower()
    if value in ("", "off", "none", "0"):
        return None
    start, end = value.split("-")
    return int(start) % 24, int(end) % 24


def _hours(value: str) -> tuple[int, ...]:
    return tuple(sorted({int(h) % 24 for h in (value or "").split(",") if h.strip()}))


@dataclass
class Settings:
    sec_user_agent: str = ""
    ntfy_server: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""
    telegram_token: str = ""
    telegram_chat_id: str = ""
    table: str = ""  # DynamoDB table name; empty means local file state
    state_path: str = ".wire-state.json"
    timezone: str = "America/New_York"
    quiet: tuple[int, int] | None = (23, 7)
    quiet_urgent: bool = False  # let priority-5 alerts ring during quiet hours
    digest_hours: tuple[int, ...] = (7, 19)
    site_url: str = "https://jikjii.github.io/bci-census/"
    openfda_api_key: str = ""
    time_budget_s: float = 90.0
    disabled: frozenset[str] = frozenset()
    job_boards: list[dict] = field(default_factory=list)
    user_agent: str = DEFAULT_USER_AGENT

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        boards = []
        if env.get("WIRE_JOB_BOARDS"):
            boards = json.loads(env["WIRE_JOB_BOARDS"])
        return cls(
            sec_user_agent=env.get("SEC_USER_AGENT", "").strip(),
            ntfy_server=env.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/"),
            ntfy_topic=env.get("NTFY_TOPIC", "").strip(),
            ntfy_token=env.get("NTFY_TOKEN", "").strip(),
            telegram_token=env.get("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=env.get("TELEGRAM_CHAT_ID", "").strip(),
            table=env.get("WIRE_TABLE", "").strip(),
            state_path=env.get("WIRE_STATE_PATH", ".wire-state.json"),
            timezone=env.get("WIRE_TZ", "America/New_York"),
            quiet=_quiet(env.get("WIRE_QUIET_HOURS", "23-7")),
            quiet_urgent=env.get("WIRE_QUIET_URGENT", "").lower() in ("1", "true", "yes"),
            digest_hours=_hours(env.get("WIRE_DIGEST_HOURS", "7,19")),
            site_url=env.get("CENSUS_SITE_URL", "https://jikjii.github.io/bci-census/").rstrip("/") + "/",
            openfda_api_key=env.get("OPENFDA_API_KEY", "").strip(),
            time_budget_s=float(env.get("WIRE_TIME_BUDGET_S", "90")),
            disabled=frozenset(s.strip() for s in env.get("WIRE_DISABLED_SOURCES", "").split(",") if s.strip()),
            job_boards=boards,
        )
