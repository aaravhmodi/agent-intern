"""Read community GitHub internship lists, company job boards, and confs.tech."""

import html
import json
import re
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.request import Request, urlopen

from pydantic import TypeAdapter, ValidationError

from opportunity_lite.models import (
    AshbyResponse,
    Conference,
    Config,
    GitHubPosting,
    GreenhouseResponse,
    LeverPosting,
    Listing,
)

_CONFERENCES = TypeAdapter(list[Conference])
_SLUG = re.compile(r"^[a-zA-Z0-9_-]+$")

# Community-maintained internship lists that publish .github/scripts/listings.json.
GITHUB_LISTS = (
    "SimplifyJobs/Summer2027-Internships",
    "vanshb03/Summer2027-Internships",
)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(value: str) -> str:
    parser = _Text()
    parser.feed(html.unescape(value))
    return " ".join(" ".join(parser.parts).split())


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "opportunity-lite/0.1"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def greenhouse(board: str, payload: Any) -> list[Listing]:
    if not _SLUG.fullmatch(board):
        raise ValueError(f"Invalid Greenhouse board token: {board!r}")
    jobs = GreenhouseResponse.model_validate(payload).jobs
    return [
        Listing(
            kind="job",
            title=job.title,
            organization=job.company_name or board,
            url=job.absolute_url,
            source=f"Greenhouse: {board}",
            location=job.location.name,
            description=plain_text(job.content)[:4000],
            posted_on=job.first_published.date() if job.first_published else None,
        )
        for job in jobs
    ]


_LEVER = TypeAdapter(list[LeverPosting])


def lever(company: str, payload: Any) -> list[Listing]:
    return [
        Listing(
            kind="job",
            title=post.text,
            organization=company,
            url=post.hostedUrl,
            source=f"Lever: {company}",
            location=post.categories.location,
            description=post.descriptionPlain[:4000],
            posted_on=date.fromtimestamp(post.createdAt / 1000) if post.createdAt else None,
        )
        for post in _LEVER.validate_python(payload)
    ]


def ashby(company: str, payload: Any) -> list[Listing]:
    return [
        Listing(
            kind="job",
            title=job.title,
            organization=company,
            url=job.jobUrl,
            source=f"Ashby: {company}",
            location=job.location,
            description=job.descriptionPlain[:4000],
            posted_on=job.publishedAt.date() if job.publishedAt else None,
        )
        for job in AshbyResponse.model_validate(payload).jobs
        if job.isListed
    ]


BOARDS = {
    "Greenhouse": ("https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=true", greenhouse),
    "Lever": ("https://api.lever.co/v0/postings/{}?mode=json", lever),
    "Ashby": ("https://api.ashbyhq.com/posting-api/job-board/{}", ashby),
}


def github_list(repo: str, payload: Any, today: date, max_age_days: int) -> list[Listing]:
    if not isinstance(payload, list):
        raise ValueError(f"{repo} listings.json is not a list")
    oldest = today - timedelta(days=max_age_days)
    listings: list[Listing] = []
    for row in payload:
        try:
            post = GitHubPosting.model_validate(row)
            if not (post.active and post.is_visible):
                continue
            posted = date.fromtimestamp(post.date_posted)
            if posted < oldest:
                continue
            details = [t for t in (*post.terms, post.season, post.category) if t and t != "N/A"]
            listings.append(
                Listing(
                    kind="job",
                    title=post.title,
                    organization=post.company_name,
                    url=post.url,
                    source=f"GitHub: {repo}",
                    location="; ".join(post.locations),
                    description=" · ".join(details),
                    posted_on=posted,
                )
            )
        except ValidationError:
            continue  # one malformed community row shouldn't drop the whole list
    return listings


def conferences(topic: str, payload: Any, today: date) -> list[Listing]:
    if not _SLUG.fullmatch(topic):
        raise ValueError(f"Invalid conference topic: {topic!r}")
    records = _CONFERENCES.validate_python(payload)
    return [
        Listing(
            kind="conference",
            title=item.name,
            organization=item.name,
            url=item.url,
            source=f"confs.tech: {topic}",
            location=", ".join(x for x in (item.city, item.country) if x),
            description=f"Call for proposals: {item.cfpUrl}" if item.cfpUrl else "",
            event_date=item.cfpEndDate or item.startDate,
        )
        for item in records
        if (item.endDate or item.startDate or item.cfpEndDate or today) >= today
    ]


def collect(config: Config, today: date) -> tuple[list[Listing], list[str]]:
    found: dict[str, Listing] = {}
    errors: list[str] = []
    for repo in GITHUB_LISTS:
        try:
            url = f"https://raw.githubusercontent.com/{repo}/dev/.github/scripts/listings.json"
            items = github_list(repo, fetch_json(url), today, config.max_age_days)
            found.update((item.key, item) for item in items)
        except (OSError, ValueError) as exc:
            errors.append(f"GitHub {repo}: {type(exc).__name__}")
    for name, tokens in (
        ("Greenhouse", config.greenhouse_boards),
        ("Lever", config.lever_boards),
        ("Ashby", config.ashby_boards),
    ):
        template, parse = BOARDS[name]
        for token in tokens:
            try:
                if not _SLUG.fullmatch(token):
                    raise ValueError("invalid board token")
                items = parse(token, fetch_json(template.format(token)))
                found.update((item.key, item) for item in items)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"{name} {token}: {type(exc).__name__}")
    for topic in config.conference_topics:
        try:
            if not _SLUG.fullmatch(topic):
                raise ValueError("invalid topic")
            url = (
                "https://raw.githubusercontent.com/tech-conferences/conference-data/main/"
                f"conferences/{today.year}/{topic}.json"
            )
            items = conferences(topic, fetch_json(url), today)
            found.update((item.key, item) for item in items)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"confs.tech {topic}: {type(exc).__name__}")
    return list(found.values()), errors
