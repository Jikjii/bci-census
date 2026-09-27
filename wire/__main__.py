"""Command line for the Wire.

    python -m wire run            one pass: poll what's due, push alerts (or print them if NTFY_TOPIC is unset)
    python -m wire run --dry-run  print alerts instead of pushing, even if NTFY_TOPIC is set
    python -m wire run --force    poll every source now, ignoring schedules
    python -m wire loop           run every minute until stopped (a laptop or server without AWS)
    python -m wire test           send one test alert to your phone
    python -m wire telegram-setup print your chat id after you message your bot
    python -m wire status         what each source did last, from the state store
    python -m wire sources        list the sources and how often each is checked
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from .config import Settings
from .httpclient import Session
from .notify import Notification, NotifyError, PrintNotifier, TelegramNotifier, build_notifier
from .runner import Runner
from .sources import all_sources
from .state import open_state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m wire", description="The BCI Wire")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "loop"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--dry-run", action="store_true", help="print alerts instead of pushing them")
        cmd.add_argument("--force", action="store_true", help="poll every source now")
        cmd.add_argument("--only", default="", help="comma-separated source names")
        cmd.add_argument("--state", default="", help="state file (default .wire-state.json)")
    sub.add_parser("test")
    sub.add_parser("telegram-setup")
    status = sub.add_parser("status")
    status.add_argument("--state", default="")
    sub.add_parser("sources")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    settings = Settings.from_env()
    if getattr(args, "state", ""):
        settings.state_path = args.state
    session = Session(settings.user_agent, settings.sec_user_agent)

    if args.command == "sources":
        for source in all_sources(settings):
            flag = " (needs SEC_USER_AGENT)" if source.needs_sec else ""
            print(f"{source.name:16} every {source.every:>4} min  {source.description}{flag}")
        return 0

    if args.command == "telegram-setup":
        if not settings.telegram_token:
            print("Set TELEGRAM_BOT_TOKEN to the token @BotFather gave you, then run this again.")
            return 1
        try:
            chats = TelegramNotifier(session, settings.telegram_token, "").chats()
        except NotifyError as exc:
            print(exc)
            return 1
        if not chats:
            print("No messages yet. Open your bot in Telegram, press Start (or send it any message), then run this again.")
            return 1
        for chat_id, name in chats:
            print(f"TELEGRAM_CHAT_ID={chat_id}    ({name})")
        return 0

    if args.command == "test":
        notifier = build_notifier(settings, session)
        notifier.send(Notification(title="BCI Wire test", priority=4, tags=["wire"],
                                   message="If this reached your phone, alerts will too.",
                                   actions=[("Draft post", "https://twitter.com/intent/tweet?text=Testing%20the%20BCI%20Wire")]))
        if isinstance(notifier, PrintNotifier):
            print("\nNo alert channel is set (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID, or NTFY_TOPIC), so the test was printed above.")
        else:
            print("Sent.")
        return 0

    state = open_state(settings)
    if args.command == "status":
        for source in all_sources(settings):
            meta = state.get(f"src#{source.name}") or {}
            print(f"{source.name:16} last run {meta.get('last_run', 'never'):25} ok {meta.get('last_ok', '-'):25} "
                  f"fails {meta.get('fail_count', 0)}  {meta.get('last_error', '')}")
        queue = (state.get("digest") or {}).get("items") or []
        print(f"\nDigest queue: {len(queue)} item(s)")
        return 0

    notifier = build_notifier(settings, session, dry_run=args.dry_run)
    runner = Runner(settings, state, session, notifier)
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    while True:
        report = runner.run(force=args.force, only=only)
        print(json.dumps(report, indent=1))
        if args.command == "run":
            return 0 if not report.get("errors") else 1
        args.force = False
        time.sleep(max(5, 60 - report.get("seconds", 0)))


if __name__ == "__main__":
    sys.exit(main())
