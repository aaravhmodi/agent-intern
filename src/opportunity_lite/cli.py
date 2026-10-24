"""Local command line interface for finding listings and preparing drafts."""

import argparse
import hashlib
import json
import os
from datetime import date
from pathlib import Path

from openai import OpenAI

from opportunity_lite.drafting import draft_message
from opportunity_lite.models import Config, Listing
from opportunity_lite.sources import collect
from opportunity_lite.store import filter_items, load, merge, save


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="intern-agent")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--data", type=Path, default=Path("data/listings.json"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("search", help="Refresh public job boards and conference data")
    listing = commands.add_parser("list", help="Show saved listings")
    listing.add_argument("--query", default="", help="Filter by title, organization, or location")
    drafting = commands.add_parser("draft", help="Prepare a reviewed message for a listing")
    drafting.add_argument("number", type=int, help="Number shown by list")
    drafting.add_argument("--profile", type=Path, default=Path("profile.md"))
    dashboard = commands.add_parser("dashboard", help="Open the local draft review and send page")
    dashboard.add_argument("--port", type=int, default=8766)
    return parser


def _config(path: Path) -> Config:
    return Config.model_validate_json(path.read_text(encoding="utf-8"))


def _display(items: list[Listing]) -> None:
    for number, item in enumerate(items, 1):
        print(f"{number:3}. {item.kind:10} {item.title} — {item.organization}")
        print(f"     {item.location} | {item.url}")


def _load_env(path: Path) -> None:
    """Fill unset variables from a local .env file; values already in the shell win."""
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and value.strip() and not name.lstrip().startswith("#"):
                os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def main() -> None:
    _load_env(Path(".env"))
    args = _parser().parse_args()
    config = _config(args.config)
    if args.command == "search":
        incoming, errors = collect(config.greenhouse_boards, config.conference_topics, date.today())
        selected = filter_items(incoming, config.keywords)
        all_items = merge(load(args.data), selected)
        save(args.data, all_items)
        print(f"Saved {len(selected)} matching public listings; {len(all_items)} total.")
        for error in errors:
            print(f"Source unavailable: {error}")
    elif args.command == "list":
        items = load(args.data)
        if args.query:
            items = filter_items(items, [args.query])
        _display(items)
    elif args.command == "draft":
        items = load(args.data)
        if not 1 <= args.number <= len(items):
            raise SystemExit("Listing number is out of range. Run `intern-agent list`.")
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit("Set OPENAI_API_KEY before generating a draft.")
        profile = args.profile.read_text(encoding="utf-8")
        item = items[args.number - 1]
        draft = draft_message(OpenAI(api_key=key), config.model, profile, item)
        draft_id = hashlib.sha256(item.key.encode()).hexdigest()[:16]
        out = args.data.parent / "drafts" / f"{draft_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"listing_url": str(item.url), **draft.model_dump()}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Draft saved to {out}. Review and copy it yourself.")
    elif args.command == "dashboard":
        from opportunity_lite.dashboard import serve

        serve(args.data.parent, args.port)


if __name__ == "__main__":
    main()
