from dataclasses import asdict, dataclass, field


@dataclass
class Profile:
    login: str
    name: str | None
    location: str | None
    followers: int
    following: int
    public_repos: int
    created_at: str
    updated_at: str
    url: str

    @classmethod
    def from_api(cls, data: dict) -> "Profile":
        return cls(
            login=data["login"],
            name=data.get("name"),
            location=data.get("location"),
            followers=data.get("followers", 0),
            following=data.get("following", 0),
            public_repos=data.get("public_repos", 0),
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
            url=data.get("html_url") or "",
        )


@dataclass
class Repo:
    name: str
    description: str | None
    stars: int
    forks: int
    language: str | None
    is_fork: bool
    pushed_at: str
    url: str
    languages: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict) -> "Repo":
        return cls(
            name=data["name"],
            description=data.get("description"),
            stars=data.get("stargazers_count", 0),
            forks=data.get("forks_count", 0),
            language=data.get("language"),
            is_fork=data.get("fork", False),
            pushed_at=data.get("pushed_at") or "",
            url=data.get("html_url") or "",
        )


@dataclass
class Report:
    profile: Profile
    repos: list[Repo]
    fetched_at: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Report":
        return cls(
            profile=Profile(**data["profile"]),
            repos=[Repo(**repo) for repo in data["repos"]],
            fetched_at=data["fetched_at"],
        )
