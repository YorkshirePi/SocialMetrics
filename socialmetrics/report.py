"""Render an AnalysisResult as Markdown and CSV."""

from __future__ import annotations

import csv

from .analyze import AnalysisResult, Metrics

_PASS_TITLES = {
    "all_interactions": "All interactions",
    "excluding_employees": "Excluding Vision RT employees",
}


def _channel_label(scope: str) -> str:
    return "ALL CHANNELS" if scope == "__all__" else scope


def _ordered_scopes(metrics: dict[str, Metrics]) -> list[str]:
    channels = sorted(s for s in metrics if s != "__all__")
    return channels + (["__all__"] if "__all__" in metrics else [])


def to_markdown(result: AnalysisResult) -> str:
    lines: list[str] = []
    lines.append(f"# LinkedIn engagement — {result.month_label}")
    lines.append("")
    lines.append(
        "Channels: Vision RT and the SGRT Community. "
        f"Reporting month: **{result.month_label}** (most recent full month)."
    )
    lines.append("")

    for pass_name, metrics in result.passes.items():
        lines.append(f"## {_PASS_TITLES.get(pass_name, pass_name)}")
        lines.append("")
        lines.append("| Channel | Posts | Likes | Comments | Reposts | Total |")
        lines.append("|---|--:|--:|--:|--:|--:|")
        for scope in _ordered_scopes(metrics):
            m = metrics[scope]
            lines.append(
                f"| {_channel_label(scope)} | {m.post_count} | {m.likes} | "
                f"{m.comments} | {m.reposts} | {m.total_interactions} |"
            )
        lines.append("")

    if result.employee_interactions_removed:
        lines.append("## Employee interactions removed in pass 2")
        lines.append("")
        lines.append("| Channel | Likes | Comments | Reposts | Total |")
        lines.append("|---|--:|--:|--:|--:|")
        removed = result.employee_interactions_removed
        for scope in _ordered_scopes(removed):
            m = removed[scope]
            lines.append(
                f"| {_channel_label(scope)} | {m.likes} | {m.comments} | "
                f"{m.reposts} | {m.total_interactions} |"
            )
        lines.append("")
        lines.append(
            "> Employees are inferred from the `actor_employer` text on each "
            "interaction (case-insensitive substring match). Accuracy depends "
            "entirely on that field being populated in the source data."
        )
        lines.append("")

    return "\n".join(lines)


def write_csv(result: AnalysisResult, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["pass", "channel", "post_count", "likes", "comments", "reposts",
             "total_interactions"]
        )
        for pass_name, metrics in result.passes.items():
            for scope in _ordered_scopes(metrics):
                m = metrics[scope]
                w.writerow(
                    [pass_name, _channel_label(scope), m.post_count, m.likes,
                     m.comments, m.reposts, m.total_interactions]
                )
