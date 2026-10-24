"""OpenAI web search for job postings and public contact addresses; read-only."""

import re
from typing import Any
from urllib.request import Request, urlopen

from openai import OpenAI
from pydantic import ValidationError

from opportunity_lite.leads.sending import is_email
from opportunity_lite.models import Contact, Listing, WebPostings

_WEB_SEARCH: list[Any] = [{"type": "web_search"}]
_NOT_HIRING = re.compile(
    r"^(partners?|partnerships|sales|support|help|press|media|pr|privacy|legal|billing|"
    r"security|abuse|investors?|ir|no-?reply)[@.+_-]"
)


def search_jobs(client: OpenAI, model: str, query: str, count: int = 15) -> list[Listing]:
    response = client.responses.parse(
        model=model,
        tools=_WEB_SEARCH,
        instructions=(
            f"Search the web for up to {count} currently open job postings matching the "
            "user's query. Prefer the employer's own careers page or its applicant tracking "
            "system (Greenhouse, Lever, Ashby, Workday) over aggregators. Only include postings "
            "you actually found, with the exact posting URL. Never invent a posting or URL. "
            "Keep each description to one or two sentences."
        ),
        input=query,
        text_format=WebPostings,
        store=False,
    )
    if response.output_parsed is None:
        return []
    listings: list[Listing] = []
    for post in WebPostings.model_validate(response.output_parsed.model_dump()).postings:
        try:
            listings.append(
                Listing.model_validate(
                    {
                        **post.model_dump(),
                        "kind": "job",
                        "source": "Web search",
                        "description": post.description[:4000],
                    }
                )
            )
        except ValidationError:
            continue
    return listings


def find_contact(client: OpenAI, model: str, listing: Listing) -> tuple[Contact, bool] | None:
    """Ask web search for a public hiring email; the flag says it appears on the cited page."""
    response = client.responses.parse(
        model=model,
        tools=_WEB_SEARCH,
        instructions=(
            "Find one public email address for asking about this opening: a recruiter, "
            "university or early-careers team, or hiring contact at the organization. Not a "
            "sales, partnerships, support, press, or privacy address. Use only addresses written "
            "on a web page, and return that exact page as source_url. Never guess or construct "
            "an address. If none is published, return empty strings."
        ),
        input=listing.model_dump_json(),
        text_format=Contact,
        store=False,
    )
    if response.output_parsed is None:
        return None
    contact = Contact.model_validate(response.output_parsed.model_dump())
    contact.email = contact.email.strip().lower()
    if not is_email(contact.email) or not contact.source_url.startswith("https://"):
        return None
    if _NOT_HIRING.match(contact.email):
        return None
    return contact, published_on(contact.source_url, contact.email)


def published_on(url: str, email: str) -> bool:
    """True when the address appears in the page; pages built by JavaScript read as False."""
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 intern-agent/0.1"})
        with urlopen(request, timeout=15) as response:
            page = response.read(2_000_000).decode("utf-8", errors="ignore")
    except (OSError, ValueError):
        return False
    return email in re.sub(r"\s*(\[at\]|\(at\))\s*", "@", page.lower())
