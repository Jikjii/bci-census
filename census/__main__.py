"""Command line: python -m census build [--offline] [--as-of YYYY-MM-DD]"""

from __future__ import annotations

import argparse
import logging

from .build import run


def main() -> None:
    parser = argparse.ArgumentParser(prog="census", description="Build the BCI Census.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Pull sources, count, diff and publish")
    build.add_argument("--offline", action="store_true", help="Skip network pulls; reuse the last pulled data")
    build.add_argument("--as-of", help="Snapshot date (default: today)")
    build.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.command == "build":
        result = run(offline=args.offline, as_of=args.as_of)
        print("\n\n".join(result["posts"]))


if __name__ == "__main__":
    main()
