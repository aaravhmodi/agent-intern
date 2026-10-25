"""Fictional data at HTTP and AI boundaries; real parsing and app storage run."""

import io
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from opportunity_lite.models import Contact, Draft, WebPosting, WebPostings
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def feed(url: str) -> Any:
    posted = int(datetime.now(UTC).timestamp())
    if "listings.json" in url:
        company = "Sample Labs" if "SimplifyJobs" in url else "Northstar Systems"
        return [
            {
                "company_name": company,
                "title": "Software Engineer Intern",
                "url": f"https://example.org/{company.split()[0].lower()}/intern",
                "date_posted": posted,
                "active": True,
                "locations": ["Toronto, ON"],
                "terms": ["Winter 2027"],
                "category": "Software",
            }
        ]
    if "api.lever.co" in url:
        return [
            {
                "text": "Backend Intern",
                "hostedUrl": "https://example.org/lever/intern",
                "categories": {"location": "Remote"},
                "createdAt": posted * 1000,
                "descriptionPlain": "Build Python APIs and reliable product features.",
            }
        ]
    if "conference-data" in url:
        return [
            {
                "name": "Developer Summit",
                "url": "https://example.org/summit",
                "startDate": str(date.today() + timedelta(days=40)),
                "city": "Toronto",
                "country": "Canada",
            }
        ]
    raise AssertionError(f"Unexpected fixture feed: {url}")


def parse(**kwargs: Any) -> SimpleNamespace:
    schema = kwargs["text_format"]
    if schema is WebPostings:
        result = WebPostings(
            postings=[
                WebPosting(
                    title="Platform Intern",
                    organization="Harbour Studio",
                    url="https://example.org/harbour/intern",
                    location="Remote",
                    description="Help build Python services and internal developer tools.",
                )
            ]
        )
    elif schema is Contact:
        unverified = "Harbour" in kwargs["input"]
        result = Contact(
            email="careers@example.org" if unverified else "jobs@example.org",
            source_url="https://example.org/contact",
        )
    elif schema is Draft:
        result = Draft(
            subject="Internship interest - Python API experience",
            email=(
                "Hi team,\n\nI'm Alex, a software engineering student who has built Python APIs "
                "and a PostgreSQL project tracker. I'd love to learn more about your internship "
                "and contribute to your team.\n\nWould you be open to a brief chat? "
                "My resume is attached.\n\nThanks,\nAlex"
            ),
            short_message=(
                "Hi! I'm Alex, a student with Python API and PostgreSQL experience. "
                "Could we chat about your internship?"
            ),
        )
    else:
        raise AssertionError("Unexpected AI schema")
    return SimpleNamespace(output_parsed=result)


def contact_page(*args: Any, **kwargs: Any) -> io.BytesIO:
    return io.BytesIO(b"<p>Hiring enquiries: jobs@example.org</p>")


def resume(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 14 Tf 50 720 Td (Alex Morgan - Built Python APIs "
        b"and a PostgreSQL project tracker.) Tj ET"
    )
    page[NameObject("/Contents")] = stream
    writer.write(path)
