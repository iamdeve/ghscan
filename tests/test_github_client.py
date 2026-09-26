import asyncio

import httpx
import pytest

from ghscan import github_client
from ghscan.github_client import (
    API_URL,
    GitHubError,
    RateLimited,
    UserNotFound,
    get_json,
    get_languages,
    get_profile,
    get_repos,
)

PROFILE = {"login": "Octo", "name": "Octo Cat", "followers": 3, "public_repos": 2}


def repo_json(name: str, stars: int = 0, fork: bool = False) -> dict:
    return {"name": name, "stargazers_count": stars, "fork": fork, "pushed_at": "2025-01-01T00:00:00Z"}


def client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=API_URL, transport=httpx.MockTransport(handler))


def run(coro_fn, handler):
    async def go():
        async with client_for(handler) as client:
            return await coro_fn(client)
    return asyncio.run(go())


def test_404_raises_user_not_found():
    handler = lambda request: httpx.Response(404, json={"message": "Not Found"})
    with pytest.raises(UserNotFound, match="User 'ghost' not found"):
        run(lambda c: get_profile(c, "ghost"), handler)


def test_403_with_no_remaining_is_rate_limit():
    handler = lambda request: httpx.Response(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1790000000"}
    )
    with pytest.raises(RateLimited, match="Resets at"):
        run(lambda c: get_profile(c, "octo"), handler)


def test_429_is_rate_limit():
    handler = lambda request: httpx.Response(429)
    with pytest.raises(RateLimited):
        run(lambda c: get_profile(c, "octo"), handler)


def test_other_403_is_not_rate_limit():
    handler = lambda request: httpx.Response(403, headers={"x-ratelimit-remaining": "42"})
    with pytest.raises(GitHubError, match="Access forbidden") as exc:
        run(lambda c: get_profile(c, "octo"), handler)
    assert not isinstance(exc.value, RateLimited)


def test_401_mentions_token():
    handler = lambda request: httpx.Response(401)
    with pytest.raises(GitHubError, match="GITHUB_TOKEN"):
        run(lambda c: get_json(c, "/user"), handler)


def test_network_failure_is_clean_error():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)
    with pytest.raises(GitHubError, match="Could not reach GitHub"):
        run(lambda c: get_profile(c, "octo"), handler)


def test_profile_is_parsed():
    handler = lambda request: httpx.Response(200, json=PROFILE)
    profile = run(lambda c: get_profile(c, "octo"), handler)
    assert profile.login == "Octo"
    assert profile.location is None


def test_pagination_stops_on_short_page(monkeypatch):
    monkeypatch.setattr(github_client, "PER_PAGE", 2)
    pages = {1: [repo_json("a"), repo_json("b")], 2: [repo_json("c")]}
    seen = []

    def handler(request):
        page = int(request.url.params["page"])
        seen.append(page)
        return httpx.Response(200, json=pages.get(page, []))

    repos = run(lambda c: get_repos(c, "octo"), handler)
    assert [r.name for r in repos] == ["a", "b", "c"]
    assert seen == [1, 2]


def test_languages_error_returns_empty_but_rate_limit_propagates():
    sem = asyncio.Semaphore(1)
    gone = lambda request: httpx.Response(451)
    limited = lambda request: httpx.Response(403, headers={"x-ratelimit-remaining": "0"})

    assert run(lambda c: get_languages(c, "octo", "blocked", sem), gone) == {}
    with pytest.raises(RateLimited):
        run(lambda c: get_languages(c, "octo", "x", asyncio.Semaphore(1)), limited)


def test_fetch_report_skips_forks_and_limits_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(github_client, "UNAUTHENTICATED_LANGUAGE_LIMIT", 2)
    repos = [repo_json("big", 100), repo_json("mid", 50), repo_json("small", 1), repo_json("fork", 999, fork=True)]
    language_calls = []

    def handler(request):
        path = request.url.path
        if path == "/users/octo":
            return httpx.Response(200, json=PROFILE)
        if path == "/users/octo/repos":
            return httpx.Response(200, json=repos)
        language_calls.append(path.split("/")[3])
        return httpx.Response(200, json={"Python": 100})

    monkeypatch.setattr(github_client, "make_client", lambda: client_for(handler))
    report = asyncio.run(github_client.fetch_report("octo"))

    assert sorted(language_calls) == ["big", "mid"]
    assert {r.name: r.languages for r in report.repos} == {
        "big": {"Python": 100}, "mid": {"Python": 100}, "small": {}, "fork": {},
    }
