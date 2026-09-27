"""A small HTTP client on the standard library, so the Lambda deploys with no packages.

It mirrors the slice of the `requests` API the census parsers use (`get(url, params=...)`,
`.json()`, `.text`, `.status_code`, `.raise_for_status()`), adds gzip, a couple of retries,
and a per-host pause so SEC stays under its fair-access limit.
"""

from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


class HTTPError(Exception):
    pass


class OutOfTime(HTTPError):
    """The run's deadline arrived; the source is simply polled again next time."""


_SECRET_PARAM = re.compile(r"([?&](?:api_key|apikey|key|token|access_token)=)[^&#]*", re.IGNORECASE)
_BOT_PATH = re.compile(r"/bot\d+:[A-Za-z0-9_-]+")


def redact(url: str) -> str:
    """URLs go into error messages, logs and health alerts; keys and bot tokens don't."""
    return _BOT_PATH.sub("/bot<token>", _SECRET_PARAM.sub(r"\1<redacted>", url))


@dataclass
class Response:
    status_code: int
    content: bytes
    url: str
    headers: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        charset = "utf-8"
        ctype = self.headers.get("content-type", "")
        if "charset=" in ctype:
            charset = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(f"HTTP {self.status_code} for {redact(self.url)}")


# Minimum seconds between requests to the same host. SEC allows at most 10 per second.
HOST_PAUSE = {"sec.gov": 0.15, "news.google.com": 1.0, "eutils.ncbi.nlm.nih.gov": 0.4}
RETRY_STATUS = {429, 500, 502, 503, 504}


class Session:
    def __init__(self, user_agent: str, sec_user_agent: str = "", timeout: float = 20.0, retries: int = 2,
                 deadline: float | None = None):
        self.user_agent = user_agent
        self.sec_user_agent = sec_user_agent
        self.timeout = timeout
        self.retries = retries
        self.deadline = deadline  # time.monotonic() value; on Lambda, a little before the function times out
        self._last: dict[str, float] = {}

    def _time_left(self, url: str) -> float | None:
        if self.deadline is None:
            return None
        left = self.deadline - time.monotonic()
        if left < 2:
            raise OutOfTime(f"out of time for {redact(url)}")
        return left

    def _pause(self, host: str) -> None:
        for suffix, gap in HOST_PAUSE.items():
            if host == suffix or host.endswith("." + suffix):
                wait = self._last.get(suffix, 0.0) + gap - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._last[suffix] = time.monotonic()
                return

    def _agent(self, host: str) -> str:
        if host == "sec.gov" or host.endswith(".sec.gov"):
            if not self.sec_user_agent:
                raise HTTPError("SEC_USER_AGENT is not set; SEC requires a contact email in the User-Agent")
            return self.sec_user_agent
        return self.user_agent

    def request(self, method: str, url: str, params: dict | None = None, data: bytes | None = None,
                headers: dict | None = None, timeout: float | None = None) -> Response:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        base = {"User-Agent": self._agent(host), "Accept-Encoding": "gzip", "Accept": "*/*"}
        base.update(headers or {})
        last_error = ""
        for attempt in range(self.retries + 1):
            self._pause(host)
            wait = timeout or self.timeout
            left = self._time_left(url)
            if left is not None:
                wait = min(wait, left - 1)
            req = urllib.request.Request(url, data=data, headers=base, method=method)
            try:
                with urllib.request.urlopen(req, timeout=wait) as resp:
                    status, body, hdrs = resp.status, resp.read(), resp.headers
            except urllib.error.HTTPError as exc:
                status, body, hdrs = exc.code, exc.read(), exc.headers
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise HTTPError(f"{last_error} for {redact(url)}") from None
            lowered = {k.lower(): v for k, v in (hdrs.items() if hdrs else [])}
            if lowered.get("content-encoding", "").lower() == "gzip" and body[:2] == b"\x1f\x8b":
                body = gzip.decompress(body)
            if status in RETRY_STATUS and attempt < self.retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            return Response(status, body, url, lowered)
        raise HTTPError(f"{last_error or 'request failed'} for {redact(url)}")

    def get(self, url: str, params: dict | None = None, timeout: float | None = None, headers: dict | None = None) -> Response:
        return self.request("GET", url, params=params, headers=headers, timeout=timeout)

    def post_json(self, url: str, payload: dict, headers: dict | None = None, timeout: float | None = None) -> Response:
        hdrs = {"Content-Type": "application/json"}
        hdrs.update(headers or {})
        return self.request("POST", url, data=json.dumps(payload).encode("utf-8"), headers=hdrs, timeout=timeout)
