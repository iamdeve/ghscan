import json
import os
import time
from pathlib import Path

from .models import Report

CACHE_DIR = Path(os.environ.get("GHSCAN_CACHE_DIR") or Path.home() / ".cache" / "ghscan")
MAX_AGE_SECONDS = 60 * 60


def cache_path(username: str) -> Path:
    return CACHE_DIR / f"{username.lower()}.json"


def load(username: str) -> Report | None:
    path = cache_path(username)
    if not path.exists():
        return None
    try:
        report = Report.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if time.time() - report.fetched_at > MAX_AGE_SECONDS:
        return None
    return report


def save(report: Report) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path(report.profile.login).write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
    except OSError:
        pass
