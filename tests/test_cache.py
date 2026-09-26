import time

import pytest

from ghscan import cache

from tests.factories import make_repo, make_report


def fresh_report(login: str = "octo"):
    return make_report(
        [make_repo("alpha", 3, language="Python", languages={"Python": 10})],
        login=login,
        fetched_at=time.time(),
    )


def test_save_then_load_returns_equal_report(tmp_cache):
    report = fresh_report()
    cache.save(report)
    assert cache.load("octo") == report


def test_load_is_case_insensitive(tmp_cache):
    report = fresh_report(login="Octo")
    cache.save(report)
    assert (tmp_cache / "octo.json").exists()
    assert cache.load("OCTO") == report
    assert cache.load("octo") == report


@pytest.mark.parametrize("content", ["{broken", "", "[]", '{"profile": {}}'])
def test_corrupted_file_returns_none(tmp_cache, content):
    (tmp_cache / "octo.json").write_text(content)
    assert cache.load("octo") is None


def test_expired_report_returns_none(tmp_cache):
    cache.save(make_report([], fetched_at=time.time() - 7200))
    assert cache.load("octo") is None


def test_missing_file_returns_none(tmp_cache):
    assert cache.load("nobody") is None


def test_save_creates_missing_parent_folders(tmp_cache, monkeypatch):
    nested = tmp_cache / "a" / "b"
    monkeypatch.setattr(cache, "CACHE_DIR", nested)
    cache.save(fresh_report())
    assert (nested / "octo.json").exists()
