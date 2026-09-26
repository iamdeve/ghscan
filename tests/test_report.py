import pytest

from ghscan.report import (
    build_stats,
    language_breakdown,
    language_line,
    render_user,
    sort_repos,
    table,
    top_languages,
)

from tests.factories import make_repo, make_report


def test_language_breakdown_sums_bytes_and_skips_forks(report):
    breakdown = dict(language_breakdown(report))
    assert "Rust" not in breakdown
    assert breakdown["Python"] == pytest.approx(70.0)
    assert breakdown["C"] == pytest.approx(20.0)
    assert breakdown["Shell"] == pytest.approx(10.0)
    assert sum(breakdown.values()) == pytest.approx(100.0)


def test_language_breakdown_is_sorted_largest_first(report):
    names = [name for name, _ in language_breakdown(report)]
    assert names[:3] == ["Python", "C", "Shell"]


def test_language_breakdown_empty_when_no_code():
    assert language_breakdown(make_report([])) == []
    assert language_breakdown(make_report([make_repo("empty")])) == []


def test_language_breakdown_falls_back_to_primary_language():
    report = make_report([
        make_repo("a", language="Python"),
        make_repo("b", language="Python"),
        make_repo("c", language="Go"),
        make_repo("d"),
    ])
    assert language_breakdown(report) == [
        ("Python", pytest.approx(200 / 3)),
        ("Go", pytest.approx(100 / 3)),
    ]


def test_top_languages_groups_rest_into_other():
    breakdown = [("C", 80.0), ("Go", 10.0), ("Rust", 5.0), ("Zig", 3.0), ("Lua", 2.0)]
    assert top_languages(breakdown) == [("C", 80.0), ("Go", 10.0), ("Rust", 5.0), ("Other", 5.0)]


def test_top_languages_no_other_when_three_or_fewer():
    breakdown = [("C", 60.0), ("Go", 40.0)]
    assert top_languages(breakdown) == breakdown
    assert top_languages([]) == []


def test_language_line_marks_tiny_share():
    assert language_line([("C", 99.7), ("Rust", 0.3)]) == "C 100%  |  Rust <1%"
    assert language_line([]) == "-"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("stars", ["forked", "beta", "alpha", "Gamma"]),
        ("updated", ["Gamma", "alpha", "beta", "forked"]),
        ("name", ["alpha", "beta", "forked", "Gamma"]),
    ],
)
def test_sort_repos(report, key, expected):
    assert [r.name for r in sort_repos(report.repos, key)] == expected


def test_table_with_empty_rows_prints_header_only():
    out = table(("Name", "Stars"), [])
    assert out.splitlines() == ["Name  Stars", "----  -----"]


def test_table_right_aligns_columns():
    out = table(("Name", "Stars"), [("a", "5"), ("bbbbbb", "1,000")], right=(1,))
    assert out.splitlines()[2] == "a           5"


def test_stats_ignore_forks(report):
    stats = build_stats(report)
    assert stats.total_stars == 255
    assert stats.total_forks == 25
    assert stats.most_starred.name == "beta"
    assert stats.last_active == "2025-06-01"


def test_stats_for_user_without_repos():
    stats = build_stats(make_report([]))
    assert stats.total_stars == 0
    assert stats.most_starred is None
    assert stats.last_active == "2020-01-01"


def test_render_user_contains_summary(report):
    out = render_user(report)
    assert out.splitlines()[0] == "Octo Cat (@octo)"
    assert "Most starred: beta (200)" in out
    assert "Python 70%  |  C 20%  |  Shell 10%" in out
