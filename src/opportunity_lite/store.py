"""Small local JSON store; no server or database required."""

from pathlib import Path

from pydantic import TypeAdapter

from opportunity_lite.models import Listing

_LISTINGS = TypeAdapter(list[Listing])


def load(path: Path) -> list[Listing]:
    if not path.exists():
        return []
    return _LISTINGS.validate_json(path.read_text(encoding="utf-8"))


def save(path: Path, listings: list[Listing]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_LISTINGS.dump_json(listings, indent=2).decode() + "\n", encoding="utf-8")


def merge(existing: list[Listing], incoming: list[Listing]) -> list[Listing]:
    by_key = {item.key: item for item in existing}
    by_key.update((item.key, item) for item in incoming)
    return sorted(by_key.values(), key=lambda item: (item.kind, item.title.lower()))


def filter_items(items: list[Listing], keywords: list[str]) -> list[Listing]:
    terms = [word.strip().casefold() for word in keywords if word.strip()]
    if not terms:
        return items
    return [
        item
        for item in items
        if any(term in searchable_text(item) for term in terms)
    ]


def searchable_text(item: Listing) -> str:
    return f"{item.title} {item.organization} {item.location} {item.description}".casefold()
