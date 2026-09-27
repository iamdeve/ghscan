import math
import time
from collections import deque
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..github_client import fetch_report
from ..models import Report
from .cache import Clock, ReportCache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_token: str | None = None
    cache_ttl_seconds: int = Field(default=3600, ge=0)
    rate_limit_per_minute: int = Field(default=30, ge=1)
    cors_origins: list[str] = ["*"]
    trust_proxy_headers: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, clock: Clock = time.monotonic) -> None:
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> float | None:
        now = self.clock()
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return hits[0] + self.window - now
        hits.append(now)
        if len(self._hits) > 10_000:
            self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > now - self.window}
        return None


def client_ip(request: Request) -> str:
    settings: Settings = request.app.state.settings
    forwarded = request.headers.get("x-forwarded-for")
    if settings.trust_proxy_headers and forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request) -> None:
    retry_after = request.app.state.limiter.hit(client_ip(request))
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests, slow down",
            headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
        )


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def get_cache(request: Request) -> ReportCache:
    return request.app.state.cache


class ReportLoader:
    def __init__(self, http: httpx.AsyncClient, cache: ReportCache) -> None:
        self.http = http
        self.cache = cache

    async def load(self, username: str, refresh: bool = False) -> tuple[Report, bool]:
        return await self.cache.get_or_fetch(
            username, lambda: fetch_report(username, self.http), refresh=refresh
        )


def get_loader(
    http: Annotated[httpx.AsyncClient, Depends(get_http)],
    cache: Annotated[ReportCache, Depends(get_cache)],
) -> ReportLoader:
    return ReportLoader(http, cache)


Loader = Annotated[ReportLoader, Depends(get_loader)]
