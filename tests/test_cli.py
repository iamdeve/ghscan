import argparse

import httpx
import pytest

from ghscan import cli, github_client
from ghscan.cli import main, positive_int, username


@pytest.mark.parametrize("name", ["torvalds", "a", "gvan-rossum", "a-b-c", "x" * 39])
def test_valid_usernames(name):
    assert username(name) == name


@pytest.mark.parametrize("name", ["", "-lead", "trail-", "dou--ble", "bad/name", "x" * 40, "sp ace"])
def test_invalid_usernames(name):
    with pytest.raises(argparse.ArgumentTypeError):
        username(name)


@pytest.mark.parametrize("value", ["0", "-3", "abc"])
def test_positive_int_rejects_bad_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int(value)


def test_bad_username_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["user", "bad--name"])
    assert exc.value.code == 2
    assert "not a valid GitHub username" in capsys.readouterr().err


def fake_github_transport(requests: list[str]) -> httpx.MockTransport:
    def handler(request):
        requests.append(request.url.path)
        login = request.url.path.split("/")[2]
        if request.url.path == f"/users/{login}":
            if login == "ghost":
                return httpx.Response(404)
            return httpx.Response(200, json={"login": login, "name": login.title(), "followers": 5})
        if request.url.path == f"/users/{login}/repos":
            return httpx.Response(200, json=[{"name": f"{login}-app", "stargazers_count": 42, "language": "Go"}])
        return httpx.Response(200, json={"Go": 1000})

    return httpx.MockTransport(handler)


@pytest.fixture
def fake_cli(monkeypatch, tmp_cache):
    requests: list[str] = []
    clients: list[httpx.AsyncClient] = []

    def make_client(token=None):
        client = github_client.make_client(token, fake_github_transport(requests))
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "make_client", make_client)
    return requests, clients


def test_user_command_end_to_end(fake_cli, capsys):
    requests, clients = fake_cli
    main(["user", "octo"])
    out = capsys.readouterr().out
    assert "Octo (@octo)" in out
    assert "Most starred: octo-app (42)" in out
    assert len(clients) == 1 and clients[0].is_closed


def test_second_run_uses_cache(fake_cli, capsys):
    requests, _ = fake_cli
    main(["user", "octo"])
    first = len(requests)
    main(["user", "octo"])
    assert len(requests) == first


def test_compare_shares_one_client(fake_cli, capsys):
    requests, clients = fake_cli
    main(["compare", "octo", "mona"])
    out = capsys.readouterr().out
    assert "@octo" in out and "@mona" in out
    assert len(clients) == 1
    assert {"/users/octo", "/users/mona"} <= set(requests)


def test_unknown_user_exits_cleanly(fake_cli, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["user", "ghost"])
    assert exc.value.code == 1
    assert capsys.readouterr().err.strip().endswith("Error: User 'ghost' not found")
