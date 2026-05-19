"""Core engagement analysis: monthly aggregation and the exclude-employees pass.

The input model is deliberately platform-agnostic so it works with either a
LinkedIn API pull (see ``linkedin_client``) or a hand/admin export:

* posts file rows:        channel, post_id, posted_at, likes, comments, reposts
* interactions rows:      channel, post_id, interaction_type, actor_name, actor_employer

Pass 1 (all interactions) uses the interactions file when supplied (so the two
passes are derived from the same source), otherwise the aggregate counts on the
posts file. Pass 2 (excluding Vision RT employees) requires the interactions
file because aggregate counts carry no actor attribution.
"""

from __future__ import annotations

import csv
import datetime as _dt
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

INTERACTION_TYPES = ("likes", "comments", "reposts")

# Maps the singular interaction_type values seen in interactions files onto the
# plural metric buckets used everywhere else.
_TYPE_ALIASES = {
    "like": "likes",
    "likes": "likes",
    "reaction": "likes",
    "comment": "comments",
    "comments": "comments",
    "repost": "reposts",
    "reposts": "reposts",
    "reshare": "reposts",
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
    interaction_type: str  # normalised to one of INTERACTION_TYPES
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

    def as_row(self) -> dict:
        return {
            "likes": self.likes,
            "comments": self.comments,
            "reposts": self.reposts,
            "post_count": self.post_count,
            "total_interactions": self.total_interactions,
        }


@dataclass
class AnalysisResult:
    year: int
    month: int
    # pass name -> channel -> Metrics  (channel "__all__" is the rolled-up total)
    passes: dict = field(default_factory=dict)
    employee_interactions_removed: dict = field(default_factory=dict)

    @property
    def month_label(self) -> str:
        return f"{self.year}-{self.month:02d}"


def most_recent_full_month(ref: _dt.date | None = None) -> tuple[int, int]:
    """The last calendar month that has fully elapsed before ``ref``."""
    ref = ref or _dt.date.today()
    first_of_this_month = ref.replace(day=1)
    last_month_end = first_of_this_month - _dt.timedelta(days=1)
    return last_month_end.year, last_month_end.month


def _parse_date(value: str) -> _dt.date:
    value = value.strip()
    # Accept full ISO timestamps as well as plain dates.
    return _dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date() \
        if ("T" in value or " " in value) else _dt.date.fromisoformat(value)


def load_posts(path: str) -> list[Post]:
    posts: list[Post] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            posts.append(
                Post(
                    channel=row["channel"].strip(),
                    post_id=row["post_id"].strip(),
                    posted_at=_parse_date(row["posted_at"]),
                    likes=int(row.get("likes") or 0),
                    comments=int(row.get("comments") or 0),
                    reposts=int(row.get("reposts") or 0),
                )
            )
    return posts


def load_interactions(path: str) -> list[Interaction]:
    rows: list[Interaction] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw_type = row["interaction_type"].strip().lower()
            if raw_type not in _TYPE_ALIASES:
                raise ValueError(f"Unknown interaction_type: {row['interaction_type']!r}")
            rows.append(
                Interaction(
                    channel=row["channel"].strip(),
                    post_id=row["post_id"].strip(),
                    interaction_type=_TYPE_ALIASES[raw_type],
                    actor_name=row.get("actor_name", "").strip(),
                    actor_employer=row.get("actor_employer", "").strip(),
                )
            )
    return rows


def posts_in_month(posts: Iterable[Post], year: int, month: int) -> list[Post]:
    return [p for p in posts if p.posted_at.year == year and p.posted_at.month == month]


def is_employee(interaction: Interaction, employer_patterns: Iterable[str]) -> bool:
    """Infer Vision RT employment from the actor's employer/title string.

    Case-insensitive substring match against any supplied pattern (e.g.
    "vision rt", "visionrt.com"). This is the documented limitation of the
    "infer from domain/title" approach: it is only as good as the employer
    text present on each interaction row.
    """
    haystack = interaction.actor_employer.lower()
    return any(pat.strip().lower() in haystack for pat in employer_patterns if pat.strip())


def _aggregate_from_posts(posts: list[Post]) -> dict[str, Metrics]:
    by_channel: dict[str, Metrics] = defaultdict(Metrics)
    for p in posts:
        for scope in (p.channel, "__all__"):
            m = by_channel[scope]
            m.likes += p.likes
            m.comments += p.comments
            m.reposts += p.reposts
    for scope, count in _post_counts(posts).items():
        by_channel[scope].post_count = count
    return dict(by_channel)


def _post_counts(posts: list[Post]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for p in posts:
        counts[p.channel] += 1
        counts["__all__"] += 1
    return counts


def _aggregate_from_interactions(
    interactions: list[Interaction],
    post_counts: dict[str, int],
    exclude: set[int] | None = None,
) -> dict[str, Metrics]:
    by_channel: dict[str, Metrics] = defaultdict(Metrics)
    for idx, it in enumerate(interactions):
        if exclude and idx in exclude:
            continue
        for scope in (it.channel, "__all__"):
            setattr(
                by_channel[scope],
                it.interaction_type,
                getattr(by_channel[scope], it.interaction_type) + 1,
            )
    for scope, count in post_counts.items():
        by_channel[scope].post_count = count
    return dict(by_channel)


def analyze(
    posts: list[Post],
    interactions: list[Interaction] | None,
    employer_patterns: Iterable[str],
    year: int,
    month: int,
) -> AnalysisResult:
    month_posts = posts_in_month(posts, year, month)
    valid_post_keys = {(p.channel, p.post_id) for p in month_posts}
    post_counts = _post_counts(month_posts)

    result = AnalysisResult(year=year, month=month)

    if interactions is None:
        result.passes["all_interactions"] = _aggregate_from_posts(month_posts)
        return result

    # Restrict interactions to posts that belong to the target month.
    scoped = [it for it in interactions if (it.channel, it.post_id) in valid_post_keys]

    result.passes["all_interactions"] = _aggregate_from_interactions(scoped, post_counts)

    employer_patterns = list(employer_patterns)
    employee_idx = {
        i for i, it in enumerate(scoped) if is_employee(it, employer_patterns)
    }
    result.passes["excluding_employees"] = _aggregate_from_interactions(
        scoped, post_counts, exclude=employee_idx
    )

    removed: dict[str, Metrics] = defaultdict(Metrics)
    for i in employee_idx:
        it = scoped[i]
        for scope in (it.channel, "__all__"):
            setattr(
                removed[scope],
                it.interaction_type,
                getattr(removed[scope], it.interaction_type) + 1,
            )
    result.employee_interactions_removed = dict(removed)
    return result
