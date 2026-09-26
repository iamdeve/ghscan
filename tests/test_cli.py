import argparse

import pytest

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
