import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from socialmetrics.analyze import (analyze, load_interactions, load_posts,
                                    most_recent_full_month, posts_in_month)

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def test_most_recent_full_month():
    assert most_recent_full_month(dt.date(2026, 5, 19)) == (2026, 4)
    assert most_recent_full_month(dt.date(2026, 1, 1)) == (2025, 12)


def test_month_filter_excludes_other_months():
    posts = load_posts(os.path.join(DATA, "sample_posts.csv"))
    april = posts_in_month(posts, 2026, 4)
    assert {p.post_id for p in april} == {
        "urn:li:share:1001", "urn:li:share:1002",
        "urn:li:share:2001", "urn:li:share:2002",
    }
    # The 2026-03 Vision RT post must not leak in.
    assert "urn:li:share:0999" not in {p.post_id for p in april}


def test_all_interactions_from_posts_file_only():
    posts = load_posts(os.path.join(DATA, "sample_posts.csv"))
    res = analyze(posts, None, ["vision rt"], 2026, 4)
    all_ch = res.passes["all_interactions"]["__all__"]
    # April only: 42+30+18+25 likes etc.
    assert all_ch.likes == 115
    assert all_ch.comments == 28
    assert all_ch.reposts == 14
    assert all_ch.post_count == 4
    assert "excluding_employees" not in res.passes


def test_exclude_employees_pass():
    posts = load_posts(os.path.join(DATA, "sample_posts.csv"))
    inter = load_interactions(os.path.join(DATA, "sample_interactions.csv"))
    res = analyze(posts, inter, ["vision rt"], 2026, 4)

    all_ch = res.passes["all_interactions"]["__all__"]
    assert all_ch.total_interactions == 10  # 10 interaction rows in April

    excl = res.passes["excluding_employees"]["__all__"]
    # Employees: Alice Stone (Vision RT) x2, Bob Lee (Vision RT Ltd) x2,
    # Chris Vale (Vision RT) x1  => 5 removed.
    assert excl.total_interactions == 5
    removed = res.employee_interactions_removed["__all__"]
    assert removed.total_interactions == 5
    assert removed.likes == 2 and removed.comments == 3 and removed.reposts == 0


def test_per_channel_breakdown():
    posts = load_posts(os.path.join(DATA, "sample_posts.csv"))
    inter = load_interactions(os.path.join(DATA, "sample_interactions.csv"))
    res = analyze(posts, inter, ["vision rt"], 2026, 4)
    vrt = res.passes["all_interactions"]["Vision RT"]
    assert vrt.post_count == 2
    assert vrt.likes == 3 and vrt.comments == 2 and vrt.reposts == 1


if __name__ == "__main__":
    import traceback

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                failures += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    raise SystemExit(1 if failures else 0)
