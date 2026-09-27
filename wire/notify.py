"""Push notifications to your phone: Telegram (recommended on AWS) or ntfy.

Each alert carries the source link and a "Draft post" button that opens X with the draft
filled in, so posting is: read, tweak, send. Digests bundle the quiet hours.

Why Telegram on AWS: ntfy.sh's free tier counts messages per IP address, and Lambda sends
from addresses shared with other AWS customers, so their traffic can use up your quota.
Telegram limits each bot, not each address. ntfy is fine from a home machine or on a paid
ntfy plan.
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass, field

from census.post import x_length

from .drafts import intent_url
from .items import Item

log = logging.getLogger(__name__)

MAX_BYTES = 3800  # ntfy turns longer messages into attachments


@dataclass
class Notification:
    title: str
    message: str
    url: str = ""
    priority: int = 3
    tags: list[str] = field(default_factory=list)
    actions: list[tuple[str, str]] = field(default_factory=list)  # (label, url)
    draft: str = ""  # the X draft alone, for channels that format it separately
    body: str = ""  # the message without the draft; empty means the same as message


def _clip(text: str, limit: int = MAX_BYTES) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[: limit - 3].decode("utf-8", errors="ignore").rstrip() + "..."


def for_item(item: Item, card: str = "") -> Notification:
    head, tail = [], []
    if item.summary:
        head.append(item.summary)
    if card:
        head.append(f"Context: {card}")
    if item.url:
        tail.append(f"Link for your reply: {item.url}")
    draft_line = [f"Draft ({x_length(item.draft)}/280): {item.draft}"] if item.draft else []
    actions = []
    if item.draft:
        actions.append(("Draft post", intent_url(item.draft)))
    if item.url:
        actions.append(("Open source", item.url))
    title = f"{item.label}: {item.title}"
    return Notification(
        title=title[:150],
        message=_clip("\n\n".join(head + draft_line + tail)),
        url=item.url,
        priority=max(1, min(5, item.priority)),
        tags=[item.kind],
        actions=actions,
        draft=item.draft,
        body="\n\n".join(head + tail),
    )


def digest(items: list[Item], label: str, draft: str) -> Notification:
    lines = []
    for n, item in enumerate(items[:15], 1):
        lines.append(f"{n}. [{item.label}] {item.title}" + (f"\n   {item.url}" if item.url else ""))
    if len(items) > 15:
        lines.append(f"...and {len(items) - 15} more")
    body = "\n".join(lines)
    return Notification(
        title=f"BCI Wire {label}: {len(items)} item{'s' if len(items) != 1 else ''}",
        message=_clip(body + (f"\n\nDraft ({x_length(draft)}/280): {draft}" if draft else "")),
        priority=3,
        tags=["digest"],
        actions=[("Draft post", intent_url(draft))] if draft else [],
        draft=draft,
        body=body,
    )


class NtfyNotifier:
    def __init__(self, session, server: str, topic: str, token: str = ""):
        self.session, self.server, self.topic, self.token = session, server.rstrip("/"), topic, token
        self.sent: list[Notification] = []

    def send(self, note: Notification) -> None:
        payload = {"topic": self.topic, "title": note.title, "message": note.message, "priority": note.priority}
        if note.tags:
            payload["tags"] = note.tags
        if note.url:
            payload["click"] = note.url
        if note.actions:
            payload["actions"] = [{"action": "view", "label": label, "url": url, "clear": False}
                                  for label, url in note.actions[:3]]
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        resp = self.session.post_json(self.server + "/", payload, headers=headers, timeout=15)
        resp.raise_for_status()
        self.sent.append(note)


class NotifyError(Exception):
    pass


TELEGRAM_API = "https://api.telegram.org"


def telegram_text(note: Notification) -> str:
    """Telegram HTML: bold title, the alert, then the draft in a block that copies on tap."""
    title = f"URGENT: {note.title}" if note.priority >= 5 else note.title
    parts = [f"<b>{html.escape(title, quote=False)}</b>"]
    body = note.body or (note.message if not note.draft else "")
    if body:
        parts.append(html.escape(_clip(body, 3000), quote=False))
    if note.draft:
        parts.append(f"Draft ({x_length(note.draft)}/280), tap to copy:\n<pre>{html.escape(note.draft, quote=False)}</pre>")
    return "\n\n".join(parts)


class TelegramNotifier:
    """Messages from your own Telegram bot. Create the bot with @BotFather, send it any message,
    then `python -m wire telegram-setup` prints the chat id."""

    def __init__(self, session, token: str, chat_id: str):
        self.session, self.token, self.chat_id = session, token, str(chat_id)
        self.sent: list[Notification] = []

    def _redact(self, text: str) -> str:
        return text.replace(self.token, "<token>") if self.token else text

    def call(self, method: str, payload: dict) -> tuple[bool, dict | str]:
        try:
            resp = self.session.post_json(f"{TELEGRAM_API}/bot{self.token}/{method}", payload, timeout=15)
        except Exception as exc:  # never let the token reach the logs through a URL in the error
            raise NotifyError(self._redact(f"Telegram unreachable: {exc}")) from None
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if resp.status_code == 200 and data.get("ok"):
            return True, data.get("result")
        return False, self._redact(f"HTTP {resp.status_code} {data.get('description', '')}".strip())

    def send(self, note: Notification) -> None:
        payload = {
            "chat_id": self.chat_id,
            "text": telegram_text(note),
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
            "disable_notification": note.priority <= 3,  # 3 is a quiet push; 4 and 5 ring
        }
        buttons = [{"text": label, "url": url} for label, url in note.actions[:3] if url.startswith(("https://", "http://"))]
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": [buttons]}
        ok, detail = self.call("sendMessage", payload)
        if not ok and buttons and any(w in str(detail).lower() for w in ("button", "url")):
            payload.pop("reply_markup")  # a link Telegram won't accept shouldn't cost the alert
            ok, detail = self.call("sendMessage", payload)
        if not ok:
            raise NotifyError(f"Telegram refused the message: {detail}")
        self.sent.append(note)

    def chats(self) -> list[tuple[str, str]]:
        """Chats that have messaged the bot recently: (chat id, name)."""
        ok, result = self.call("getUpdates", {"limit": 100, "timeout": 0})
        if not ok:
            raise NotifyError(f"Telegram refused getUpdates: {result}")
        found: dict[str, str] = {}
        for update in result or []:
            message = update.get("message") or update.get("channel_post") or update.get("my_chat_member") or {}
            chat = message.get("chat") or {}
            if "id" in chat:
                name = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
                found[str(chat["id"])] = name or chat.get("username") or chat.get("type", "")
        return list(found.items())


class FanOut:
    """Sends to every configured channel; fails only when all of them fail."""

    def __init__(self, channels: list):
        self.channels = channels
        self.sent: list[Notification] = []

    def send(self, note: Notification) -> None:
        errors = []
        for channel in self.channels:
            try:
                channel.send(note)
            except Exception as exc:
                errors.append(exc)
                log.warning("%s failed: %s", type(channel).__name__, exc)
        if len(errors) == len(self.channels):
            raise errors[0]
        self.sent.append(note)


def build_notifier(settings, session, dry_run: bool = False):
    """Telegram and/or ntfy, whichever are configured; printing when neither is (or for dry runs)."""
    if dry_run:
        return PrintNotifier()
    channels = []
    if settings.telegram_token and settings.telegram_chat_id:
        channels.append(TelegramNotifier(session, settings.telegram_token, settings.telegram_chat_id))
    if settings.ntfy_topic:
        channels.append(NtfyNotifier(session, settings.ntfy_server, settings.ntfy_topic, settings.ntfy_token))
    if not channels:
        return PrintNotifier()
    return channels[0] if len(channels) == 1 else FanOut(channels)


class PrintNotifier:
    """Prints instead of pushing: for dry runs and tests."""

    def __init__(self, echo: bool = True):
        self.echo = echo
        self.sent: list[Notification] = []

    def send(self, note: Notification) -> None:
        self.sent.append(note)
        if self.echo:
            print(f"\n=== [{note.priority}] {note.title}\n{note.message}")
            for label, url in note.actions:
                print(f"  -> {label}: {url[:120]}")
