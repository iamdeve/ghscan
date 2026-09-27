import asyncio
import time
from collections import Counter

import httpx
import pytest
from fastapi.testclient import TestClient

from ghscan.api.cache import ReportCache
from ghscan.api.deps import RateLimiter, Settings, get_http
from ghscan.api.main import create_app
from ghscan.github_client import make_client

from tests.factories import make_report

USERS = {
    "octo": {
        "profile": {"login": "Octo", "name": "Octo Cat", "location": "Earth", "followers": 12,
                    "html_url": "https://github.com/Octo", "created_at": "2015-01-01T00:00:00Z"},
        "repos": [
            {"name": "big", "stargazers_count": 900, "forks_count": 30, "language": "Python",
             "pushed_at": "2026-05-01T00:00:00Z"},
            {"name": "small", "stargazers_count": 100, "language": "Go", "pushed_at": "2021-01-01T00:00:00Z"},
            {"name": "copied", "stargazers_count": 5000, "fork": True, "language": "C",
             "pushed_at": "2026-09-01T00:00:00Z"},
        ],
        "languages": {"big": {"Python": 750, "Shell": 50}, "small": {"Go": 200}},
    },
    "mona": {
        "profile": {"login": "mona", "followers": 3},
        "repos": [{"name": "site", "stargazers_count": 7, "language": "HTML"}],
        "languages": {"site": {"HTML": 10}},
    },
}


class FakeGitHub:
    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self.delay = 0.0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls[path] += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.status:
            return httpx.Response(self.status, headers=self.headers)

        parts = path.strip("/").split("/")
        if parts[0] == "users":
            user = USERS.get(parts[1].lower())
            if user is None:
                return httpx.Response(404)
            if len(parts) == 2:
                return httpx.Response(200, json=user["profile"])
            page = int(request.url.params.get("page", 1))
            return httpx.Response(200, json=user["repos"] if page == 1 else [])
        owner, repo = parts[1].lower(), parts[2]
        return httpx.Response(200, json=USERS[owner]["languages"].get(repo, {}))

    def profile_calls(self, login: str) -> int:
        return self.calls[f"/users/{login}"]


def build(**overrides) -> tuple:
    settings = Settings(_env_file=None, github_token=None, **overrides)
    app = create_app(settings)
    github = FakeGitHub()

    async def fake_http():
        async with make_client(transport=httpx.MockTransport(github)) as client:
            yield client

    app.dependency_overrides[get_http] = fake_http
    return app, github


@pytest.fixture
def api():
    app, github = build()
    with TestClient(app) as client:
        yield client, github


def test_health(api):
    client, _ = api
    assert client.get("/health").json() == {"status": "ok"}


def test_user_summary(api):
    client, _ = api
    r = client.get("/users/octo")
    assert r.status_code == 200
    body = r.json()
    assert body["login"] == "Octo"
    assert body["total_stars"] == 1000
    assert body["total_forks"] == 30
    assert body["most_starred"]["name"] == "big"
    assert body["languages"] == [
        {"name": "Python", "percent": 75.0},
        {"name": "Go", "percent": 20.0},
        {"name": "Shell", "percent": 5.0},
    ]
    assert body["last_active"] == "2026-09-01"
    assert body["created_at"] == "2015-01-01T00:00:00Z"


def test_repos_sorting_limit_and_forks(api):
    client, _ = api
    names = lambda **p: [r["name"] for r in client.get("/users/octo/repos", params=p).json()]
    assert names() == ["big", "small"]
    assert names(include_forks=True) == ["copied", "big", "small"]
    assert names(sort="name") == ["big", "small"]
    assert names(sort="updated", include_forks=True) == ["copied", "big", "small"]
    assert names(limit=1) == ["big"]
    assert "languages" not in client.get("/users/octo/repos").json()[0]


@pytest.mark.parametrize("params", [{"sort": "size"}, {"limit": 0}, {"limit": 101}])
def test_repos_rejects_bad_query(api, params):
    client, _ = api
    assert client.get("/users/octo/repos", params=params).status_code == 422


def test_compare_fetches_both(api):
    client, github = api
    body = client.get("/compare", params={"a": "octo", "b": "mona"}).json()
    assert body["a"]["login"] == "Octo"
    assert body["b"]["login"] == "mona"
    assert github.profile_calls("octo") == github.profile_calls("mona") == 1


def test_markdown_report(api):
    client, _ = api
    r = client.get("/users/octo/report.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.text.startswith("# Octo Cat")
    assert "| [big](" in r.text


@pytest.mark.parametrize(
    "url",
    ["/users/bad--name", "/users/-lead", "/users/trail-", "/users/" + "x" * 40, "/compare?a=octo&b=no_underscores",
     "/compare?a=octo"],
)
def test_invalid_usernames_are_422(api, url):
    client, github = api
    assert client.get(url).status_code == 422
    assert not github.calls


def test_unknown_user_is_404(api):
    client, _ = api
    r = client.get("/users/ghost")
    assert r.status_code == 404
    assert r.json() == {"detail": "User 'ghost' not found"}


def test_github_rate_limit_is_429_with_retry_after(api):
    client, github = api
    github.status = 403
    github.headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(time.time()) + 120)}
    r = client.get("/users/octo")
    assert r.status_code == 429
    assert 100 <= int(r.headers["retry-after"]) <= 120


def test_github_rate_limit_without_reset_header(api):
    client, github = api
    github.status = 429
    assert client.get("/users/octo").headers["retry-after"] == "60"


@pytest.mark.parametrize("upstream", [500, 503, 451])
def test_other_github_errors_are_502(api, upstream):
    client, github = api
    github.status = upstream
    r = client.get("/users/octo")
    assert r.status_code == 502
    assert "GitHub returned" in r.json()["detail"]


def test_second_request_is_served_from_cache(api):
    client, github = api
    first = client.get("/users/octo")
    second = client.get("/users/OCTO/repos")
    third = client.get("/users/octo/report.md")
    assert (first.headers["x-cache"], second.headers["x-cache"], third.headers["x-cache"]) == ("MISS", "HIT", "HIT")
    assert github.profile_calls("octo") == 1


def test_refresh_bypasses_cache(api):
    client, github = api
    client.get("/users/octo")
    r = client.get("/users/octo", params={"refresh": True})
    assert r.headers["x-cache"] == "MISS"
    assert github.profile_calls("octo") == 2


def test_failed_fetch_is_not_cached(api):
    client, github = api
    github.status = 500
    assert client.get("/users/octo").status_code == 502
    github.status = None
    assert client.get("/users/octo").status_code == 200


def test_rate_limiter_returns_429_after_limit():
    app, _ = build(rate_limit_per_minute=3)
    with TestClient(app) as client:
        codes = [client.get("/users/octo").status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        limited = client.get("/users/mona")
        assert limited.status_code == 429
        assert 1 <= int(limited.headers["retry-after"]) <= 60
        assert client.get("/health").status_code == 200


def test_rate_limiter_is_per_client_ip():
    app, _ = build(rate_limit_per_minute=1, trust_proxy_headers=True)
    with TestClient(app) as client:
        a = {"X-Forwarded-For": "spoofed, 1.1.1.1"}
        b = {"X-Forwarded-For": "2.2.2.2"}
        assert client.get("/users/octo", headers=a).status_code == 200
        assert client.get("/users/octo", headers=b).status_code == 200
        assert client.get("/users/octo", headers={"X-Forwarded-For": "other, 1.1.1.1"}).status_code == 429


def test_rate_limiter_window_slides():
    now = [0.0]
    limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    assert limiter.hit("ip") is None
    now[0] = 30
    assert limiter.hit("ip") is None
    assert limiter.hit("ip") == pytest.approx(30)
    now[0] = 61
    assert limiter.hit("ip") is None
    assert limiter.hit("other") is None


def test_cors_allows_get_from_any_origin(api):
    client, _ = api
    r = client.get("/health", headers={"Origin": "https://my-frontend.vercel.app"})
    assert r.headers["access-control-allow-origin"] == "*"
    preflight = client.options(
        "/users/octo",
        headers={"Origin": "https://x.dev", "Access-Control-Request-Method": "DELETE"},
    )
    assert preflight.status_code == 400


def test_cache_entries_expire():
    now = [0.0]
    cache = ReportCache(ttl_seconds=10, clock=lambda: now[0])
    cache.set("Octo", make_report([], login="Octo"))
    assert cache.get("octo") is not None
    now[0] = 10
    assert cache.get("octo") is None
    assert len(cache) == 0


def test_cache_evicts_oldest_when_full():
    now = [0.0]
    cache = ReportCache(ttl_seconds=100, max_entries=2, clock=lambda: now[0])
    for i, name in enumerate(["a", "b", "c"]):
        now[0] = i
        cache.set(name, make_report([], login=name))
    assert cache.get("a") is None
    assert cache.get("b") is not None and cache.get("c") is not None


def test_concurrent_fetches_are_coalesced():
    cache = ReportCache(ttl_seconds=60)
    calls = 0

    async def slow_fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return make_report([], login="octo")

    async def main():
        return await asyncio.gather(*(cache.get_or_fetch("octo", slow_fetch) for _ in range(10)))

    results = asyncio.run(main())
    assert calls == 1
    assert all(report is results[0][0] for report, _ in results)


def test_concurrent_api_requests_share_one_github_fetch():
    app, github = build()
    github.delay = 0.05

    async def main():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await asyncio.gather(*(client.get("/users/octo") for _ in range(10)))

    responses = asyncio.run(main())
    assert [r.status_code for r in responses] == [200] * 10
    assert github.profile_calls("Octo") + github.profile_calls("octo") == 1


def test_coalesced_failure_reaches_every_waiter_and_is_not_cached():
    cache = ReportCache(ttl_seconds=60)

    async def failing_fetch():
        await asyncio.sleep(0.01)
        raise RuntimeError("boom")

    async def main():
        return await asyncio.gather(
            *(cache.get_or_fetch("octo", failing_fetch) for _ in range(3)), return_exceptions=True
        )

    results = asyncio.run(main())
    assert all(isinstance(r, RuntimeError) for r in results)
    assert cache.get("octo") is None


def test_settings_read_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_example")
    monkeypatch.setenv("CACHE_TTL_SECONDS", "120")
    settings = Settings(_env_file=None)
    assert settings.github_token == "ghp_example"
    assert settings.cache_ttl_seconds == 120


def test_settings_reject_bad_values(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "zero")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_app_client_uses_configured_token():
    app = create_app(Settings(_env_file=None, github_token="secret"))
    with TestClient(app):
        assert app.state.http.headers["authorization"] == "Bearer secret"
