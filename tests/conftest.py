import pytest

from ghscan import cache
from ghscan.models import Report

from tests.factories import make_repo, make_report


@pytest.fixture
def report() -> Report:
    return make_report([
        make_repo("alpha", 50, forks=5, language="Python", pushed_at="2024-03-01T00:00:00Z",
                  languages={"Python": 7000, "Shell": 1000}),
        make_repo("beta", 200, forks=20, language="C", pushed_at="2023-01-01T00:00:00Z",
                  languages={"C": 2000}),
        make_repo("Gamma", 5, language="Go", pushed_at="2025-06-01T00:00:00Z",
                  languages={"Go": 0}),
        make_repo("forked", 999, language="Rust", is_fork=True, pushed_at="2022-01-01T00:00:00Z",
                  languages={"Rust": 100000}),
    ])


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    return tmp_path
