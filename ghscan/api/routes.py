import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import PlainTextResponse

from ..models import USERNAME_MAX_LENGTH, USERNAME_PATTERN
from ..report import render_markdown, sort_repos
from .deps import Loader, rate_limit
from .schemas import Comparison, RepoOut, UserSummary

router = APIRouter(dependencies=[Depends(rate_limit)])

USERNAME_RULES = dict(pattern=USERNAME_PATTERN, max_length=USERNAME_MAX_LENGTH, examples=["torvalds"])
Username = Annotated[str, Path(**USERNAME_RULES, description="GitHub username")]
Refresh = Annotated[bool, Query(description="Skip the cache and fetch fresh data")]


def mark_cache(response: Response, hit: bool) -> None:
    response.headers["X-Cache"] = "HIT" if hit else "MISS"


@router.get("/users/{username}", response_model=UserSummary)
async def get_user(username: Username, loader: Loader, response: Response, refresh: Refresh = False):
    report, hit = await loader.load(username, refresh)
    mark_cache(response, hit)
    return UserSummary.from_report(report)


@router.get("/users/{username}/repos", response_model=list[RepoOut])
async def get_repos(
    username: Username,
    loader: Loader,
    response: Response,
    sort: Literal["stars", "updated", "name"] = "stars",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    include_forks: bool = False,
    refresh: Refresh = False,
):
    report, hit = await loader.load(username, refresh)
    mark_cache(response, hit)
    repos = report.repos if include_forks else [r for r in report.repos if not r.is_fork]
    return [RepoOut.from_repo(r) for r in sort_repos(repos, sort)[:limit]]


@router.get("/compare", response_model=Comparison)
async def compare(
    a: Annotated[str, Query(**USERNAME_RULES)],
    b: Annotated[str, Query(**USERNAME_RULES)],
    loader: Loader,
    refresh: Refresh = False,
):
    (first, _), (second, _) = await asyncio.gather(loader.load(a, refresh), loader.load(b, refresh))
    return Comparison(a=UserSummary.from_report(first), b=UserSummary.from_report(second))


@router.get("/users/{username}/report.md", response_class=PlainTextResponse)
async def markdown_report(username: Username, loader: Loader, refresh: Refresh = False):
    report, hit = await loader.load(username, refresh)
    return PlainTextResponse(
        render_markdown(report),
        media_type="text/markdown; charset=utf-8",
        headers={"X-Cache": "HIT" if hit else "MISS"},
    )
