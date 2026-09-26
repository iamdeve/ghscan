from ghscan.models import Profile, Repo, Report


def make_repo(name: str, stars: int = 0, **kwargs) -> Repo:
    defaults = dict(
        description=None,
        forks=0,
        language=None,
        is_fork=False,
        pushed_at="",
        url=f"https://github.com/octo/{name}",
        languages={},
    )
    defaults.update(kwargs)
    return Repo(name=name, stars=stars, **defaults)


def make_report(repos: list[Repo], login: str = "octo", fetched_at: float = 0.0) -> Report:
    profile = Profile(
        login=login,
        name="Octo Cat",
        location="Earth",
        followers=10,
        following=1,
        public_repos=len(repos),
        created_at="2015-01-01T00:00:00Z",
        updated_at="2020-01-01T00:00:00Z",
        url=f"https://github.com/{login}",
    )
    return Report(profile=profile, repos=repos, fetched_at=fetched_at)
