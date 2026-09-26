# ghscan

A small command-line tool for looking up any GitHub user. It shows their top repos, language breakdown, total stars and recent activity, and it can compare two users side by side or export a Markdown report.

Built with Python 3.10+, `asyncio` and `httpx`. Requests run in parallel, and results are cached for an hour, so a repeat lookup is instant.

## Install

With pip, straight from GitHub:

```bash
pip install git+https://github.com/iamdeve/ghscan
ghscan user torvalds
```

Or from a local clone, for development:

```bash
git clone https://github.com/iamdeve/ghscan.git
cd ghscan
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

`python -m ghscan ...` works the same as `ghscan ...`.

## GitHub token (recommended)

Without a token, GitHub allows only 60 API requests per hour, and ghscan uses one request per repo to read its languages. To raise the limit to 5,000 per hour, create a free token:

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**.
2. Create a token. It needs no permissions, because public data is enough.
3. Export it in your shell:

```bash
export GITHUB_TOKEN=github_pat_xxx          # macOS / Linux
$env:GITHUB_TOKEN="github_pat_xxx"          # Windows PowerShell
```

Never commit your token.

> **Without a token**, ghscan only fetches languages for the user's **20 most-starred repos**, so one lookup stays within the free limit. For users with many repos, the language percentages are then approximate.

## Usage

### `user`: profile summary

```text
$ ghscan user torvalds
Linus Torvalds (@torvalds)
Location: Portland, OR    Followers: 325,265    Public repos: 12
----------------------------------------------------------------
Total stars: 262,263      Most starred: linux (250,260)
Languages:  C 98%  |  Assembly 1%  |  Rust <1%  |  Other 1%
Last active: 2026-09-25
```

### `repos`: list repositories

`--sort` accepts `stars` (the default), `updated` or `name`. `--limit` defaults to 10.

```text
$ ghscan repos torvalds --sort stars --limit 5
@torvalds - top 5 repos by stars
#  Name           Stars   Forks  Language  Updated
-  -----------  -------  ------  --------  ----------
1  linux        250,260  65,868  C         2026-09-25
2  AudioNoise     4,503     222  C         2026-05-08
3  GuitarPedal    2,371     112  C         2026-09-24
4  uemacs         2,150     325  C         2026-08-06
5  test-tlb       1,063     222  C         2024-08-19
```

### `compare`: two users side by side

Both users are fetched in parallel.

```text
$ ghscan compare torvalds gvanrossum
              @torvalds        @gvanrossum
------------  ---------------  ----------------------
Name          Linus Torvalds   Guido van Rossum
Location      Portland, OR     San Francisco Bay Area
Followers     325,265          27,072
Public repos  12               28
Total stars   262,263          1,653
Total forks   66,878           139
Most starred  linux (250,260)  patma (1,041)
Top language  C (98%)          HTML (57%)
Joined        2011-09-03       2012-11-26
Last active   2026-09-25       2026-08-22
```

### `export`: save a report

```text
$ ghscan export torvalds --format md
Saved torvalds_report.md
```

The file contains the profile summary, the full language list and a table of every repo:

```markdown
| Repo | Stars | Forks | Language | Updated | Description |
|---|--:|--:|---|---|---|
| [linux](https://github.com/torvalds/linux) | 250,260 | 65,868 | C | 2026-09-25 | Linux kernel source tree |
| [AudioNoise](https://github.com/torvalds/AudioNoise) | 4,503 | 222 | C | 2026-05-08 | Random digital audio effects |
```

`--format json` writes the raw data instead, and `-o path` sets the output file.

### Skipping the cache

Every command accepts `--no-cache` to skip the cache and fetch fresh data:

```bash
ghscan user torvalds --no-cache
```

### Errors

Bad input or failed requests print a one-line message to stderr, never a traceback:

```text
$ ghscan user this-user-does-not-exist-9x7
Error: User 'this-user-does-not-exist-9x7' not found

$ ghscan user torvalds          # no internet
Error: Could not reach GitHub. Check your internet connection.

$ ghscan user trail-
ghscan user: error: argument username: 'trail-' is not a valid GitHub username
```

## How it works

- The profile and the repo list are fetched at the same time with `asyncio.gather`.
- The repo list is fetched page by page (100 repos per page) and stops at the first page that isn't full.
- Languages are fetched in parallel for non-fork repos. An `asyncio.Semaphore(5)` keeps at most 5 of those requests running at once.
- Forks are listed and marked `(fork)`, but they are left out of star totals and language percentages.
- Results are cached in `~/.cache/ghscan/<username>.json` for an hour. Set `GHSCAN_CACHE_DIR` to use a different folder. A corrupted cache file is treated as a cache miss.
- A 403 response counts as a rate limit only when `x-ratelimit-remaining` is `0`. In that case the message also shows when the limit resets.

## Project layout

```text
ghscan/
├── __main__.py       entry point for `python -m ghscan`
├── cli.py            argparse commands and error handling
├── github_client.py  async GitHub API calls, pagination, errors
├── cache.py          JSON cache in ~/.cache/ghscan, 1-hour expiry
├── models.py         Profile, Repo and Report dataclasses
├── report.py         pure stats functions and text/markdown rendering
└── errors.py         GhscanError base class
tests/                pytest suite, GitHub mocked with httpx.MockTransport
```

## Running tests

```bash
pip install -e ".[dev]"
pytest
```
