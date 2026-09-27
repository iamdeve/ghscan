from datetime import date, datetime, timezone

from pydantic import BaseModel

from ..models import Report, Repo
from ..report import (
    language_breakdown,
    last_active_date,
    most_starred,
    top_languages,
    total_forks,
    total_stars,
)


class LanguageShare(BaseModel):
    name: str
    percent: float


class RepoOut(BaseModel):
    name: str
    description: str | None
    stars: int
    forks: int
    language: str | None
    is_fork: bool
    pushed_at: datetime | None
    url: str

    @classmethod
    def from_repo(cls, repo: Repo) -> "RepoOut":
        return cls.model_validate(repo.model_dump(exclude={"languages"}))


class UserSummary(BaseModel):
    login: str
    name: str | None
    location: str | None
    url: str
    followers: int
    following: int
    public_repos: int
    created_at: datetime | None
    total_stars: int
    total_forks: int
    most_starred: RepoOut | None
    languages: list[LanguageShare]
    last_active: date | None
    fetched_at: datetime

    @classmethod
    def from_report(cls, report: Report) -> "UserSummary":
        p = report.profile
        top = most_starred(report)
        active = last_active_date(report)
        return cls(
            login=p.login,
            name=p.name,
            location=p.location,
            url=p.url,
            followers=p.followers,
            following=p.following,
            public_repos=p.public_repos,
            created_at=p.created_at,
            total_stars=total_stars(report),
            total_forks=total_forks(report),
            most_starred=RepoOut.from_repo(top) if top else None,
            languages=[
                LanguageShare(name=name, percent=round(pct, 1))
                for name, pct in top_languages(language_breakdown(report), top=8)
            ],
            last_active=active.date() if active else None,
            fetched_at=datetime.fromtimestamp(report.fetched_at, tz=timezone.utc),
        )


class Comparison(BaseModel):
    a: UserSummary
    b: UserSummary
