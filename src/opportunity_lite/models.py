"""Validated boundaries for configuration, public feeds, storage, and model output."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    greenhouse_boards: list[str] = Field(default_factory=list)
    conference_topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    model: str = "gpt-4o-mini"


class GreenhouseLocation(BaseModel):
    name: str = ""


class GreenhouseJob(BaseModel):
    id: int
    title: str
    absolute_url: HttpUrl
    location: GreenhouseLocation = Field(default_factory=GreenhouseLocation)
    content: str = ""


class GreenhouseResponse(BaseModel):
    jobs: list[GreenhouseJob]


class Conference(BaseModel):
    name: str
    url: HttpUrl
    startDate: date | None = None
    endDate: date | None = None
    city: str = ""
    country: str = ""
    cfpUrl: str = ""
    cfpEndDate: date | None = None

    @field_validator("startDate", "endDate", "cfpEndDate", mode="before")
    @classmethod
    def blank_date(cls, value: object) -> object:
        return None if value == "" else value


class Listing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["job", "conference"]
    title: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    url: HttpUrl
    source: str
    location: str = ""
    description: str = ""
    event_date: date | None = None

    @property
    def key(self) -> str:
        return str(self.url).rstrip("/").lower()


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=1, max_length=3000)
    short_message: str = Field(min_length=1, max_length=1000)
