"""Validated boundaries for configuration, public feeds, storage, and model output."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    greenhouse_boards: list[str] = Field(default_factory=list)
    lever_boards: list[str] = Field(default_factory=list)
    ashby_boards: list[str] = Field(default_factory=list)
    conference_topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    max_age_days: int = Field(default=30, ge=1)
    model: str = "gpt-4o-mini"


class GreenhouseLocation(BaseModel):
    name: str = ""


class GreenhouseJob(BaseModel):
    id: int
    title: str
    absolute_url: HttpUrl
    location: GreenhouseLocation = Field(default_factory=GreenhouseLocation)
    content: str = ""
    company_name: str = ""
    first_published: datetime | None = None


class GreenhouseResponse(BaseModel):
    jobs: list[GreenhouseJob]


class LeverCategories(BaseModel):
    location: str = ""


class LeverPosting(BaseModel):
    text: str
    hostedUrl: HttpUrl
    categories: LeverCategories = Field(default_factory=LeverCategories)
    descriptionPlain: str = ""
    createdAt: int | None = None  # milliseconds since the epoch


class AshbyJob(BaseModel):
    title: str
    jobUrl: HttpUrl
    location: str = ""
    descriptionPlain: str = ""
    isListed: bool = True
    publishedAt: datetime | None = None


class AshbyResponse(BaseModel):
    jobs: list[AshbyJob]


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


class GitHubPosting(BaseModel):
    """One row of a community internship list's .github/scripts/listings.json."""

    company_name: str
    title: str
    url: HttpUrl
    date_posted: int
    active: bool = False
    is_visible: bool = True
    locations: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    season: str = ""
    category: str = ""


class WebPosting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    organization: str
    url: str
    location: str
    description: str


class WebPostings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    postings: list[WebPosting]


class Contact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    source_url: str


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
    posted_on: date | None = None

    @property
    def key(self) -> str:
        return str(self.url).rstrip("/").lower()


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=1, max_length=3000)
    short_message: str = Field(min_length=1, max_length=1000)
