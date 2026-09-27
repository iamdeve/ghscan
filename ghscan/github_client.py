import asyncio
import os
import time
from datetime import datetime

import httpx
from pydantic import BaseModel, ValidationError

from .errors import GhscanError
from .models import Profile, Repo, Report

API_URL = "https://api.github.com"
PER_PAGE = 100
MAX_CONCURRENT = 5
UNAUTHENTICATED_LANGUAGE_LIMIT = 20


class GitHubError(GhscanError):
    pass


class UserNotFound(GitHubError):
    def __init__(self, username: str) -> None:
        super().__init__(f"User '{username}' not found")


class RateLimited(GitHubError):
    def __init__(self, reset_at: str | None = None) -> None:
        message = "Rate limit hit. Set GITHUB_TOKEN or try later."
        if reset_at and reset_at.isdigit():
            message += f" Resets at {datetime.fromtimestamp(int(reset_at)):%H:%M}."
        super().__init__(message)


def get_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN")


def build_headers(token: str | None = None) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ghscan"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def make_client(
    token: str | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=API_URL, headers=build_headers(token), timeout=20.0, transport=transport
    )


def is_authenticated(client: httpx.AsyncClient) -> bool:
    return "authorization" in client.headers


async def get_json(
    client: httpx.AsyncClient, path: str, params: dict | None = None
) -> dict | list | None:
    try:
        resp = await client.get(path, params=params)
    except httpx.TimeoutException:
        raise GitHubError("GitHub took too long to respond. Try again.") from None
    except httpx.HTTPError:
        raise GitHubError("Could not reach GitHub. Check your internet connection.") from None

    if resp.status_code == 404:
        return None
    if resp.status_code == 401:
        raise GitHubError("GITHUB_TOKEN is invalid or expired.")
    if resp.status_code in (403, 429):
        if resp.status_code == 429 or resp.headers.get("x-ratelimit-remaining") == "0":
            raise RateLimited(resp.headers.get("x-ratelimit-reset"))
        raise GitHubError(f"Access forbidden: {path}")
    if resp.is_error:
        raise GitHubError(f"GitHub returned {resp.status_code} for {path}")
    return resp.json()


def parse(model: type[BaseModel], data: dict):
    try:
        return model.model_validate(data)
    except ValidationError as err:
        raise GitHubError(f"Unexpected data from GitHub: {err.errors()[0]['msg']}") from None


async def get_profile(client: httpx.AsyncClient, username: str) -> Profile:
    data = await get_json(client, f"/users/{username}")
    if data is None:
        raise UserNotFound(username)
    return parse(Profile, data)


async def get_repos(client: httpx.AsyncClient, username: str) -> list[Repo]:
    repos: list[Repo] = []
    page = 1
    while True:
        params = {"per_page": PER_PAGE, "page": page, "type": "owner"}
        batch = await get_json(client, f"/users/{username}/repos", params)
        if batch is None:
            raise UserNotFound(username)
        repos.extend(parse(Repo, item) for item in batch)
        if len(batch) < PER_PAGE:
            break
        page += 1
    return repos


async def get_languages(
    client: httpx.AsyncClient, owner: str, repo: str, sem: asyncio.Semaphore
) -> dict[str, int]:
    async with sem:
        try:
            data = await get_json(client, f"/repos/{owner}/{repo}/languages")
        except RateLimited:
            raise
        except GitHubError:
            return {}
    return data or {}


async def fetch_report(username: str, client: httpx.AsyncClient) -> Report:
    profile, repos = await asyncio.gather(
        get_profile(client, username),
        get_repos(client, username),
    )

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    own = sorted((r for r in repos if not r.is_fork), key=lambda r: r.stars, reverse=True)
    targets = own if is_authenticated(client) else own[:UNAUTHENTICATED_LANGUAGE_LIMIT]
    results = await asyncio.gather(
        *(get_languages(client, profile.login, repo.name, sem) for repo in targets)
    )
    for repo, langs in zip(targets, results):
        repo.languages = langs

    return Report(profile=profile, repos=repos, fetched_at=time.time())
