from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Profile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    login: str
    name: str | None = None
    location: str | None = None
    followers: int = Field(default=0, ge=0)
    following: int = Field(default=0, ge=0)
    public_repos: int = Field(default=0, ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    url: str = Field(default="", alias="html_url")


class Repo(BaseModel):
    model_config = ConfigDict(populate_by_name=True, validate_assignment=True)

    name: str = Field(min_length=1)
    description: str | None = None
    stars: int = Field(default=0, ge=0, alias="stargazers_count")
    forks: int = Field(default=0, ge=0, alias="forks_count")
    language: str | None = None
    is_fork: bool = Field(default=False, alias="fork")
    pushed_at: datetime | None = None
    url: str = Field(default="", alias="html_url")
    languages: dict[str, int] = Field(default_factory=dict)

    @field_validator("languages")
    @classmethod
    def drop_empty_languages(cls, v: dict[str, int]) -> dict[str, int]:
        return {lang: size for lang, size in v.items() if size > 0}


class Report(BaseModel):
    profile: Profile
    repos: list[Repo]
    fetched_at: float
