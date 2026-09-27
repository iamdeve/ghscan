import asyncio
import time
from collections.abc import Awaitable, Callable

from ..models import Report

Clock = Callable[[], float]


class ReportCache:
    def __init__(self, ttl_seconds: float, max_entries: int = 1000, clock: Clock = time.monotonic) -> None:
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self._items: dict[str, tuple[Report, float]] = {}
        self._inflight: dict[str, asyncio.Task[Report]] = {}

    def get(self, username: str) -> Report | None:
        key = username.lower()
        entry = self._items.get(key)
        if entry is None:
            return None
        report, expires_at = entry
        if self.clock() >= expires_at:
            del self._items[key]
            return None
        return report

    def set(self, username: str, report: Report) -> None:
        if len(self._items) >= self.max_entries:
            oldest = min(self._items, key=lambda k: self._items[k][1])
            del self._items[oldest]
        self._items[username.lower()] = (report, self.clock() + self.ttl)

    async def get_or_fetch(
        self, username: str, fetch: Callable[[], Awaitable[Report]], refresh: bool = False
    ) -> tuple[Report, bool]:
        key = username.lower()
        if not refresh:
            cached = self.get(key)
            if cached is not None:
                return cached, True

        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._fetch(key, fetch))
            self._inflight[key] = task
        return await asyncio.shield(task), False

    async def _fetch(self, key: str, fetch: Callable[[], Awaitable[Report]]) -> Report:
        try:
            report = await fetch()
            self.set(key, report)
            return report
        finally:
            self._inflight.pop(key, None)

    def __len__(self) -> int:
        return len(self._items)
