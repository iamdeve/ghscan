from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import Report, Repo


@dataclass
class Stats:
    total_stars: int
    total_forks: int
    most_starred: Repo | None
    languages: list[tuple[str, float]]
    last_active: str


NEVER = datetime.min.replace(tzinfo=timezone.utc)

SORT_KEYS = {
    "stars": (lambda r: (r.stars, r.forks), True),
    "updated": (lambda r: r.pushed_at or NEVER, True),
    "name": (lambda r: r.name.lower(), False),
}


def fmt_date(dt: datetime | None) -> str:
    return dt.date().isoformat() if dt else "-"


def own_repos(report: Report) -> list[Repo]:
    return [r for r in report.repos if not r.is_fork]


def total_stars(report: Report) -> int:
    return sum(r.stars for r in own_repos(report))


def total_forks(report: Report) -> int:
    return sum(r.forks for r in own_repos(report))


def most_starred(report: Report) -> Repo | None:
    return max(own_repos(report), key=lambda r: r.stars, default=None)


def language_breakdown(report: Report) -> list[tuple[str, float]]:
    repos = own_repos(report)
    totals: Counter[str] = Counter()
    for repo in repos:
        totals.update(repo.languages)
    if not totals:
        totals = Counter(r.language for r in repos if r.language)

    total = sum(totals.values())
    if total == 0:
        return []
    return [(name, count / total * 100) for name, count in totals.most_common()]


def top_languages(breakdown: list[tuple[str, float]], top: int = 3) -> list[tuple[str, float]]:
    shown = breakdown[:top]
    rest = sum(pct for _, pct in breakdown[top:])
    return shown + [("Other", rest)] if rest > 0 else shown


def last_active_date(report: Report) -> datetime | None:
    return max((r.pushed_at for r in report.repos if r.pushed_at), default=report.profile.updated_at)


def last_active(report: Report) -> str:
    return fmt_date(last_active_date(report))


def build_stats(report: Report) -> Stats:
    return Stats(
        total_stars=total_stars(report),
        total_forks=total_forks(report),
        most_starred=most_starred(report),
        languages=language_breakdown(report),
        last_active=last_active(report),
    )


def sort_repos(repos: list[Repo], by: str) -> list[Repo]:
    key, reverse = SORT_KEYS[by]
    return sorted(repos, key=key, reverse=reverse)


def pct_label(pct: float) -> str:
    return "<1%" if 0 < pct < 0.5 else f"{pct:.0f}%"


def language_line(languages: list[tuple[str, float]]) -> str:
    if not languages:
        return "-"
    return "  |  ".join(f"{name} {pct_label(pct)}" for name, pct in top_languages(languages))


def top_repo_label(repo: Repo | None) -> str:
    return f"{repo.name} ({repo.stars:,})" if repo else "-"


def table(headers: tuple[str, ...], rows: list[tuple[str, ...]], right: tuple[int, ...] = ()) -> str:
    widths = [max([len(h), *(len(row[i]) for row in rows)]) for i, h in enumerate(headers)]

    def fmt(cells: tuple[str, ...]) -> str:
        return "  ".join(
            c.rjust(w) if i in right else c.ljust(w) for i, (c, w) in enumerate(zip(cells, widths))
        ).rstrip()

    return "\n".join([fmt(headers), "  ".join("-" * w for w in widths), *(fmt(r) for r in rows)])


def render_user(report: Report) -> str:
    p = report.profile
    s = build_stats(report)
    meta = f"Location: {p.location or '-'}    Followers: {p.followers:,}    Public repos: {p.public_repos}"
    return "\n".join([
        f"{p.name or p.login} (@{p.login})",
        meta,
        "-" * max(62, len(meta)),
        f"Total stars: {s.total_stars:<12,} Most starred: {top_repo_label(s.most_starred)}",
        f"Languages:  {language_line(s.languages)}",
        f"Last active: {s.last_active}",
    ])


def render_repos(report: Report, sort_by: str, limit: int) -> str:
    repos = sort_repos(report.repos, sort_by)[:limit]
    if not repos:
        return f"@{report.profile.login} has no public repos."

    rows = [
        (
            str(i),
            r.name + (" (fork)" if r.is_fork else ""),
            f"{r.stars:,}",
            f"{r.forks:,}",
            r.language or "-",
            fmt_date(r.pushed_at),
        )
        for i, r in enumerate(repos, 1)
    ]
    title = f"@{report.profile.login} - top {len(repos)} repos by {sort_by}\n"
    return title + table(("#", "Name", "Stars", "Forks", "Language", "Updated"), rows, right=(0, 2, 3))


def render_compare(a: Report, b: Report) -> str:
    sa, sb = build_stats(a), build_stats(b)

    def top_lang(s: Stats) -> str:
        return f"{s.languages[0][0]} ({s.languages[0][1]:.0f}%)" if s.languages else "-"

    rows = [
        ("Name", a.profile.name or "-", b.profile.name or "-"),
        ("Location", a.profile.location or "-", b.profile.location or "-"),
        ("Followers", f"{a.profile.followers:,}", f"{b.profile.followers:,}"),
        ("Public repos", str(a.profile.public_repos), str(b.profile.public_repos)),
        ("Total stars", f"{sa.total_stars:,}", f"{sb.total_stars:,}"),
        ("Total forks", f"{sa.total_forks:,}", f"{sb.total_forks:,}"),
        ("Most starred", top_repo_label(sa.most_starred), top_repo_label(sb.most_starred)),
        ("Top language", top_lang(sa), top_lang(sb)),
        ("Joined", fmt_date(a.profile.created_at), fmt_date(b.profile.created_at)),
        ("Last active", sa.last_active, sb.last_active),
    ]
    return table(("", f"@{a.profile.login}", f"@{b.profile.login}"), rows)


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: Report) -> str:
    p = report.profile
    s = build_stats(report)
    repos = sort_repos(report.repos, "stars")

    lines = [
        f"# {p.name or p.login} ([@{p.login}]({p.url}))",
        "",
        f"- **Location:** {p.location or '-'}",
        f"- **Followers:** {p.followers:,}",
        f"- **Public repos:** {p.public_repos}",
        f"- **Total stars:** {s.total_stars:,}",
        f"- **Most starred:** {top_repo_label(s.most_starred)}",
        f"- **Last active:** {s.last_active}",
        "",
        "## Languages",
        "",
    ]
    lines += [f"- {name}: {'<0.1' if pct < 0.05 else f'{pct:.1f}'}%" for name, pct in s.languages[:10]] or ["No language data."]

    lines += ["", "## Repositories", ""]
    if repos:
        lines += ["| Repo | Stars | Forks | Language | Updated | Description |", "|---|--:|--:|---|---|---|"]
        lines += [
            f"| [{r.name}]({r.url}){' (fork)' if r.is_fork else ''} | {r.stars:,} | {r.forks:,} "
            f"| {r.language or '-'} | {fmt_date(r.pushed_at)} | {md_escape(r.description or '')} |"
            for r in repos
        ]
    else:
        lines.append("No public repos.")

    return "\n".join(lines) + "\n"
