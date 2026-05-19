"""Command-line entrypoint.

Two subcommands:

  fetch    Pull posts + engagement from LinkedIn into a posts CSV
           (needs network + a 3-legged admin token; see linkedin_client).
  analyze  Aggregate a posts CSV (and optional interactions CSV) into the
           monthly report, with an exclude-Vision-RT-employees pass.

Examples
--------
  python -m socialmetrics.cli analyze \
      --posts data/sample_posts.csv \
      --interactions data/sample_interactions.csv \
      --employer-pattern "vision rt" --employer-pattern "visionrt.com" \
      --out-md report.md --out-csv report.csv

  python -m socialmetrics.cli fetch \
      --token "$LINKEDIN_TOKEN" \
      --channel "Vision RT=urn:li:organization:11111" \
      --channel "SGRT Community=urn:li:organization:22222" \
      --month 2026-04 --out data/posts_2026-04.csv
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys

from .analyze import (analyze, load_interactions, load_posts,
                       most_recent_full_month)
from .report import to_markdown, write_csv


def _parse_month(value: str | None) -> tuple[int, int]:
    if not value:
        return most_recent_full_month()
    y, m = value.split("-")
    return int(y), int(m)


def _parse_channels(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--channel must be LABEL=URN, got: {pair!r}")
        label, urn = pair.split("=", 1)
        out[label.strip()] = urn.strip()
    return out


def _cmd_analyze(args: argparse.Namespace) -> int:
    year, month = _parse_month(args.month)
    posts = load_posts(args.posts)
    interactions = load_interactions(args.interactions) if args.interactions else None
    patterns = args.employer_pattern or ["vision rt", "visionrt"]
    result = analyze(posts, interactions, patterns, year, month)

    md = to_markdown(result)
    if args.out_md:
        with open(args.out_md, "w", encoding="utf-8") as fh:
            fh.write(md + "\n")
    else:
        print(md)
    if args.out_csv:
        write_csv(result, args.out_csv)
    return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    from .linkedin_client import LinkedInClient, LinkedInError

    year, month = _parse_month(args.month)
    channels = _parse_channels(args.channel)
    try:
        client = LinkedInClient(args.token)
        n = client.export_posts(channels, year, month, args.out)
    except LinkedInError as exc:
        print(f"LinkedIn fetch failed: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {n} posts for {year}-{month:02d} to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="socialmetrics")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="aggregate a posts CSV into a report")
    a.add_argument("--posts", required=True)
    a.add_argument("--interactions")
    a.add_argument("--employer-pattern", action="append",
                   help="repeatable; case-insensitive substring for employee inference")
    a.add_argument("--month", help="YYYY-MM (default: most recent full month)")
    a.add_argument("--out-md")
    a.add_argument("--out-csv")
    a.set_defaults(func=_cmd_analyze)

    f = sub.add_parser("fetch", help="pull posts+engagement from LinkedIn")
    f.add_argument("--token", required=True)
    f.add_argument("--channel", action="append", required=True,
                   help="repeatable; LABEL=urn:li:organization:ID")
    f.add_argument("--month", help="YYYY-MM (default: most recent full month)")
    f.add_argument("--out", required=True)
    f.set_defaults(func=_cmd_fetch)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
