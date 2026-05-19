#!/usr/bin/env python3
"""SocialMetrics — single-file LinkedIn monthly engagement tool.

Subcommands:
  fetch    Pull org posts + engagement from LinkedIn into a posts CSV.
  analyze  Aggregate a posts CSV (+ optional interactions CSV) into a report,
           with an exclude-Vision-RT-employees pass.

Channels default to **Vision RT only**. Pass --channel repeatedly to add more
(e.g. the SGRT Community). See README.md for the LinkedIn access requirements
(3-legged admin token, Community Management API product, network egress).

Examples
--------
  ./socialmetrics.py analyze --posts data/sample_posts.csv \
      --interactions data/sample_interactions.csv \
      --employer-pattern "vision rt" --out-md report.md

  ./socialmetrics.py fetch --token "$LINKEDIN_TOKEN" \
      --channel "Vision RT=urn:li:organization:XXXX" \
      --month 2026-04 --out data/posts_2026-04.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

__version__ = "0.2.0"

# --------------------------------------------------------------------------- #
# Analysis core
# --------------------------------------------------------------------------- #

INTERACTION_TYPES = ("likes", "comments", "reposts")

_TYPE_ALIASES = {
    "like": "likes", "likes": "likes", "reaction": "likes",
    "comment": "comments", "comments": "comments",
    "repost": "reposts", "reposts": "reposts", "reshare": "reposts",
    "share": "reposts",
}


@dataclass(frozen=True)
class Post:
    channel: str
    post_id: str
    posted_at: _dt.date
    likes: int = 0
    comments: int = 0
    reposts: int = 0


@dataclass(frozen=True)
class Interaction:
    channel: str
    post_id: str
    interaction_type: str
    actor_name: str
    actor_employer: str


@dataclass
class Metrics:
    likes: int = 0
    comments: int = 0
    reposts: int = 0
    post_count: int = 0

    @property
    def total_interactions(self) -> int:
        return self.likes + self.comments + self.reposts


@dataclass
class AnalysisResult:
    year: int
    month: int
    passes: dict = field(default_factory=dict)
    employee_interactions_removed: dict = field(default_factory=dict)

    @property
    def month_label(self) -> str:
        return f"{self.year}-{self.month:02d}"


def most_recent_full_month(ref: _dt.date | None = None) -> tuple[int, int]:
    ref = ref or _dt.date.today()
    last_month_end = ref.replace(day=1) - _dt.timedelta(days=1)
    return last_month_end.year, last_month_end.month


def _parse_date(value: str) -> _dt.date:
    value = value.strip()
    if "T" in value or " " in value:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    return _dt.date.fromisoformat(value)


def load_posts(path: str) -> list[Post]:
    posts: list[Post] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            posts.append(Post(
                channel=row["channel"].strip(),
                post_id=row["post_id"].strip(),
                posted_at=_parse_date(row["posted_at"]),
                likes=int(row.get("likes") or 0),
                comments=int(row.get("comments") or 0),
                reposts=int(row.get("reposts") or 0),
            ))
    return posts


def load_interactions(path: str) -> list[Interaction]:
    rows: list[Interaction] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw = row["interaction_type"].strip().lower()
            if raw not in _TYPE_ALIASES:
                raise ValueError(f"Unknown interaction_type: {row['interaction_type']!r}")
            rows.append(Interaction(
                channel=row["channel"].strip(),
                post_id=row["post_id"].strip(),
                interaction_type=_TYPE_ALIASES[raw],
                actor_name=row.get("actor_name", "").strip(),
                actor_employer=row.get("actor_employer", "").strip(),
            ))
    return rows


def posts_in_month(posts: Iterable[Post], year: int, month: int) -> list[Post]:
    return [p for p in posts if p.posted_at.year == year and p.posted_at.month == month]


def is_employee(it: Interaction, patterns: Iterable[str]) -> bool:
    hay = it.actor_employer.lower()
    return any(p.strip().lower() in hay for p in patterns if p.strip())


def _post_counts(posts: list[Post]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for p in posts:
        counts[p.channel] += 1
        counts["__all__"] += 1
    return counts


def _agg_from_posts(posts: list[Post]) -> dict[str, Metrics]:
    by: dict[str, Metrics] = defaultdict(Metrics)
    for p in posts:
        for scope in (p.channel, "__all__"):
            m = by[scope]
            m.likes += p.likes
            m.comments += p.comments
            m.reposts += p.reposts
    for scope, c in _post_counts(posts).items():
        by[scope].post_count = c
    return dict(by)


def _agg_from_interactions(interactions: list[Interaction],
                           post_counts: dict[str, int],
                           exclude: set[int] | None = None) -> dict[str, Metrics]:
    by: dict[str, Metrics] = defaultdict(Metrics)
    for idx, it in enumerate(interactions):
        if exclude and idx in exclude:
            continue
        for scope in (it.channel, "__all__"):
            setattr(by[scope], it.interaction_type,
                    getattr(by[scope], it.interaction_type) + 1)
    for scope, c in post_counts.items():
        by[scope].post_count = c
    return dict(by)


def analyze(posts: list[Post], interactions: list[Interaction] | None,
            employer_patterns: Iterable[str], year: int, month: int) -> AnalysisResult:
    month_posts = posts_in_month(posts, year, month)
    valid = {(p.channel, p.post_id) for p in month_posts}
    post_counts = _post_counts(month_posts)
    result = AnalysisResult(year=year, month=month)

    if interactions is None:
        result.passes["all_interactions"] = _agg_from_posts(month_posts)
        return result

    scoped = [it for it in interactions if (it.channel, it.post_id) in valid]
    result.passes["all_interactions"] = _agg_from_interactions(scoped, post_counts)

    patterns = list(employer_patterns)
    emp_idx = {i for i, it in enumerate(scoped) if is_employee(it, patterns)}
    result.passes["excluding_employees"] = _agg_from_interactions(
        scoped, post_counts, exclude=emp_idx)

    removed: dict[str, Metrics] = defaultdict(Metrics)
    for i in emp_idx:
        it = scoped[i]
        for scope in (it.channel, "__all__"):
            setattr(removed[scope], it.interaction_type,
                    getattr(removed[scope], it.interaction_type) + 1)
    result.employee_interactions_removed = dict(removed)
    return result


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

_PASS_TITLES = {
    "all_interactions": "All interactions",
    "excluding_employees": "Excluding Vision RT employees",
}


def _label(scope: str) -> str:
    return "ALL CHANNELS" if scope == "__all__" else scope


def _ordered(metrics: dict[str, Metrics]) -> list[str]:
    chans = sorted(s for s in metrics if s != "__all__")
    return chans + (["__all__"] if "__all__" in metrics else [])


def to_markdown(result: AnalysisResult) -> str:
    out: list[str] = [
        f"# LinkedIn engagement — {result.month_label}", "",
        f"Reporting month: **{result.month_label}** (most recent full month).", "",
    ]
    for name, metrics in result.passes.items():
        out += [f"## {_PASS_TITLES.get(name, name)}", "",
                "| Channel | Posts | Likes | Comments | Reposts | Total |",
                "|---|--:|--:|--:|--:|--:|"]
        for s in _ordered(metrics):
            m = metrics[s]
            out.append(f"| {_label(s)} | {m.post_count} | {m.likes} | "
                       f"{m.comments} | {m.reposts} | {m.total_interactions} |")
        out.append("")
    if result.employee_interactions_removed:
        out += ["## Employee interactions removed in pass 2", "",
                "| Channel | Likes | Comments | Reposts | Total |",
                "|---|--:|--:|--:|--:|"]
        rem = result.employee_interactions_removed
        for s in _ordered(rem):
            m = rem[s]
            out.append(f"| {_label(s)} | {m.likes} | {m.comments} | "
                       f"{m.reposts} | {m.total_interactions} |")
        out += ["", "> Employees inferred from `actor_employer` text "
                "(case-insensitive substring). Accuracy depends on that field "
                "being populated.", ""]
    return "\n".join(out)


def write_csv(result: AnalysisResult, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["pass", "channel", "post_count", "likes", "comments",
                    "reposts", "total_interactions"])
        for name, metrics in result.passes.items():
            for s in _ordered(metrics):
                m = metrics[s]
                w.writerow([name, _label(s), m.post_count, m.likes,
                            m.comments, m.reposts, m.total_interactions])


# --------------------------------------------------------------------------- #
# LinkedIn Community Management API client
# --------------------------------------------------------------------------- #

_API_BASE = "https://api.linkedin.com"
_DEFAULT_VERSION = "202401"


class LinkedInError(RuntimeError):
    pass


class LinkedInClient:
    """Needs a 3-legged member access token whose holder ADMINS the target
    page(s), an app approved for the Community Management API, and network
    egress to api.linkedin.com. Client id/secret alone are not sufficient.
    """

    def __init__(self, access_token: str, api_version: str = _DEFAULT_VERSION,
                 timeout: int = 30):
        if not access_token:
            raise LinkedInError("A 3-legged member access token is required.")
        self._token = access_token
        self._version = api_version
        self._timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{_API_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params, safe=":(),")
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._token}",
            "LinkedIn-Version": self._version,
            "X-Restli-Protocol-Version": "2.0.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LinkedInError(
                f"HTTP {exc.code} for {path}: "
                f"{exc.read().decode('utf-8', 'replace')}") from exc
        except urllib.error.URLError as exc:
            raise LinkedInError(
                f"Network error reaching LinkedIn for {path}: {exc}. "
                "Confirm egress to api.linkedin.com is allowed.") from exc

    def iter_org_posts(self, org_urn: str):
        start, page = 0, 100
        while True:
            payload = self._get("/rest/posts", {
                "q": "author", "author": org_urn,
                "count": page, "start": start})
            elements = payload.get("elements", [])
            yield from elements
            if len(elements) < page:
                return
            start += page

    def post_engagement(self, post_urn: str) -> dict:
        data = self._get(f"/rest/socialActions/{urllib.parse.quote(post_urn)}")
        likes = data.get("likesSummary", {}).get("totalLikes", 0)
        cs = data.get("commentsSummary", {})
        comments = cs.get("aggregatedTotalComments",
                          cs.get("totalFirstLevelComments", 0))
        return {"likes": int(likes), "comments": int(comments)}

    @staticmethod
    def _created_date(post: dict) -> _dt.date | None:
        ts = post.get("createdAt") or post.get("publishedAt")
        if not ts:
            return None
        return _dt.datetime.fromtimestamp(ts / 1000, _dt.timezone.utc).date()

    def export_posts(self, channels: dict[str, str], year: int, month: int,
                     out_path: str) -> int:
        rows = 0
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["channel", "post_id", "posted_at", "likes",
                        "comments", "reposts"])
            for label, org_urn in channels.items():
                for post in self.iter_org_posts(org_urn):
                    d = self._created_date(post)
                    if not d or d.year != year or d.month != month:
                        continue
                    post_urn = post.get("id") or post.get("urn", "")
                    eng = self.post_engagement(post_urn)
                    reposts = (post.get("reshareCount")
                               or post.get("totalShareStatistics", {})
                                       .get("shareCount") or 0)
                    w.writerow([label, post_urn, d.isoformat(),
                                eng["likes"], eng["comments"], int(reposts)])
                    rows += 1
        return rows


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

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
    year, month = _parse_month(args.month)
    channels = (_parse_channels(args.channel) if args.channel
                else {"Vision RT": args.vision_rt_urn})
    if not all(channels.values()):
        raise SystemExit("Provide --channel LABEL=URN or --vision-rt-urn.")
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
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="aggregate a posts CSV into a report")
    a.add_argument("--posts", required=True)
    a.add_argument("--interactions")
    a.add_argument("--employer-pattern", action="append",
                   help="repeatable; substring for employee inference")
    a.add_argument("--month", help="YYYY-MM (default: most recent full month)")
    a.add_argument("--out-md")
    a.add_argument("--out-csv")
    a.set_defaults(func=_cmd_analyze)

    f = sub.add_parser("fetch", help="pull posts+engagement from LinkedIn")
    f.add_argument("--token", required=True)
    f.add_argument("--channel", action="append",
                   help="repeatable; LABEL=urn:li:organization:ID. "
                        "Defaults to Vision RT only via --vision-rt-urn.")
    f.add_argument("--vision-rt-urn",
                   help="Vision RT organization URN (used when --channel omitted)")
    f.add_argument("--month", help="YYYY-MM (default: most recent full month)")
    f.add_argument("--out", required=True)
    f.set_defaults(func=_cmd_fetch)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
