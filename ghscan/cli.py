import argparse
import asyncio
import re
import sys
from pathlib import Path

import httpx

from . import cache
from .errors import GhscanError
from .github_client import UNAUTHENTICATED_LANGUAGE_LIMIT, fetch_report, get_token, make_client
from .models import USERNAME_MAX_LENGTH, USERNAME_PATTERN, Report
from .report import render_compare, render_markdown, render_repos, render_user

USERNAME_RE = re.compile(USERNAME_PATTERN)


def username(value: str) -> str:
    if len(value) > USERNAME_MAX_LENGTH or not USERNAME_RE.match(value):
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid GitHub username")
    return value


def positive_int(value: str) -> int:
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError(f"expected a positive number, got '{value}'")
    return int(value)


async def load_report(name: str, client: httpx.AsyncClient, use_cache: bool = True) -> Report:
    if use_cache:
        cached = cache.load(name)
        if cached:
            return cached
    print(f"Fetching @{name} from GitHub...", file=sys.stderr)
    language_limit = None if get_token() else UNAUTHENTICATED_LANGUAGE_LIMIT
    report = await fetch_report(name, client, language_limit=language_limit)
    cache.save(report)
    return report


async def cmd_user(args: argparse.Namespace, client: httpx.AsyncClient) -> None:
    report = await load_report(args.username, client, not args.no_cache)
    print(render_user(report))


async def cmd_repos(args: argparse.Namespace, client: httpx.AsyncClient) -> None:
    report = await load_report(args.username, client, not args.no_cache)
    print(render_repos(report, args.sort, args.limit))


async def cmd_compare(args: argparse.Namespace, client: httpx.AsyncClient) -> None:
    use_cache = not args.no_cache
    first, second = await asyncio.gather(
        load_report(args.first, client, use_cache),
        load_report(args.second, client, use_cache),
    )
    print(render_compare(first, second))


async def cmd_export(args: argparse.Namespace, client: httpx.AsyncClient) -> None:
    report = await load_report(args.username, client, not args.no_cache)
    if args.format == "md":
        content = render_markdown(report)
    else:
        content = report.model_dump_json(indent=2)

    path = Path(args.output or f"{report.profile.login}_report.{args.format}")
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as err:
        raise GhscanError(f"Could not write {path}: {err.strerror}") from None
    print(f"Saved {path}")


async def run(args: argparse.Namespace) -> None:
    async with make_client(get_token()) as client:
        await args.handler(args, client)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ghscan", description="Analyze GitHub profiles from your terminal")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-cache", action="store_true", help="skip the cache and fetch fresh data")

    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    p_user = sub.add_parser("user", parents=[common], help="show a profile summary")
    p_user.add_argument("username", type=username)
    p_user.set_defaults(handler=cmd_user)

    p_repos = sub.add_parser("repos", parents=[common], help="list a user's repos")
    p_repos.add_argument("username", type=username)
    p_repos.add_argument("--sort", choices=["stars", "updated", "name"], default="stars")
    p_repos.add_argument("--limit", type=positive_int, default=10)
    p_repos.set_defaults(handler=cmd_repos)

    p_compare = sub.add_parser("compare", parents=[common], help="compare two users side by side")
    p_compare.add_argument("first", type=username)
    p_compare.add_argument("second", type=username)
    p_compare.set_defaults(handler=cmd_compare)

    p_export = sub.add_parser("export", parents=[common], help="export a report to a file")
    p_export.add_argument("username", type=username)
    p_export.add_argument("--format", choices=["md", "json"], default="md")
    p_export.add_argument("-o", "--output", help="output file (default: <user>_report.<format>)")
    p_export.set_defaults(handler=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(run(args))
    except GhscanError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        sys.exit(130)
