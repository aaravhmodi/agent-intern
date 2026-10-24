"""Read public Greenhouse boards and the confs.tech open data repository."""

import html
import json
import re
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.request import Request, urlopen

from pydantic import TypeAdapter

from opportunity_lite.models import Conference, GreenhouseResponse, Listing

_CONFERENCES = TypeAdapter(list[Conference])
_SLUG = re.compile(r"^[a-zA-Z0-9_-]+$")


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
            organization=board,
            url=job.absolute_url,
            source=f"Greenhouse: {board}",
            location=job.location.name,
            description=plain_text(job.content)[:4000],
        )
        for job in jobs
    ]


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


def collect(boards: list[str], topics: list[str], today: date) -> tuple[list[Listing], list[str]]:
    found: dict[str, Listing] = {}
    errors: list[str] = []
    for board in boards:
        try:
            if not _SLUG.fullmatch(board):
                raise ValueError("invalid board token")
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            items = greenhouse(board, fetch_json(url))
            found.update((item.key, item) for item in items)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"Greenhouse {board}: {type(exc).__name__}")
    for topic in topics:
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
