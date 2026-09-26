from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ghscan.models import Profile, Repo, Report

from tests.factories import make_repo, make_report

API_REPO = {
    "name": "linux",
    "stargazers_count": 250000,
    "forks_count": 60000,
    "fork": False,
    "html_url": "https://github.com/torvalds/linux",
    "pushed_at": "2026-09-25T10:00:00Z",
    "language": "C",
    "some_extra_field": "ignored",
}


def test_repo_reads_github_aliases():
    repo = Repo.model_validate(API_REPO)
    assert repo.stars == 250000
    assert repo.forks == 60000
    assert repo.is_fork is False
    assert repo.url == "https://github.com/torvalds/linux"
    assert repo.pushed_at == datetime(2026, 9, 25, 10, tzinfo=timezone.utc)


def test_repo_accepts_field_names_too():
    assert Repo(name="x", stars=3, is_fork=True).stars == 3


def test_profile_parses_dates_and_nulls():
    profile = Profile.model_validate(
        {"login": "octo", "name": None, "created_at": "2015-01-01T00:00:00Z", "html_url": "u"}
    )
    assert profile.created_at.year == 2015
    assert profile.updated_at is None
    assert profile.url == "u"


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"name": "", "stargazers_count": 1}, "name"),
        ({"name": "a", "stargazers_count": -1}, "stargazers_count"),
        ({"name": "a", "stargazers_count": "many"}, "stargazers_count"),
        ({"name": "a", "pushed_at": "yesterday"}, "pushed_at"),
    ],
)
def test_repo_rejects_bad_data(data, field):
    with pytest.raises(ValidationError) as exc:
        Repo.model_validate(data)
    assert exc.value.errors()[0]["loc"] == (field,)


def test_zero_byte_languages_are_dropped_on_create_and_assign():
    repo = Repo(name="x", languages={"C": 10, "Go": 0})
    assert repo.languages == {"C": 10}
    repo.languages = {"Python": 0, "Rust": 5}
    assert repo.languages == {"Rust": 5}


def test_report_json_round_trip_keeps_aliased_fields():
    report = make_report([make_repo("a", 7, forks=2, is_fork=True, languages={"C": 1})], fetched_at=1.5)
    restored = Report.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.repos[0].stars == 7
    assert restored.repos[0].is_fork is True


def test_nested_error_points_at_the_bad_repo():
    with pytest.raises(ValidationError) as exc:
        Report.model_validate({"profile": {"login": "o"}, "repos": [{"name": "a"}, {"name": ""}], "fetched_at": 0})
    assert exc.value.errors()[0]["loc"] == ("repos", 1, "name")
