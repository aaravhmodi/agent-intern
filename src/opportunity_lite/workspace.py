"""Files in one working folder, and the actions the web app and command line share."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openai import OpenAI
from pypdf import PdfReader

from opportunity_lite.drafting import draft_message
from opportunity_lite.leads.sending import StoredDraft
from opportunity_lite.models import Config, Listing
from opportunity_lite.sources import collect
from opportunity_lite.store import filter_items, load, merge, save
from opportunity_lite.web import find_contact, search_jobs

ENV_KEYS = ("OPENAI_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def profile(self) -> Path:
        return self.root / "profile.md"

    @property
    def resume(self) -> Path:
        return self.root / "resume.pdf"

    @property
    def env(self) -> Path:
        return self.root / ".env"

    @property
    def listings(self) -> Path:
        return self.root / "data" / "listings.json"

    @property
    def drafts(self) -> Path:
        return self.root / "data" / "drafts"

    @property
    def sent(self) -> Path:
        return self.root / "data" / "sent.json"

    def config(self) -> Config:
        if not self.config_path.is_file():
            return Config()
        return Config.model_validate_json(self.config_path.read_text(encoding="utf-8"))

    def save_config(self, config: Config) -> None:
        self.config_path.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_env(path: Path) -> None:
    """Fill unset variables from a local .env file; values already in the shell win."""
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and value.strip() and not name.lstrip().startswith("#"):
                os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def save_env(path: Path, updates: dict[str, str]) -> None:
    """Write non-empty values into .env, keeping other lines, and apply them now."""
    updates = {k: v.strip() for k, v in updates.items() if k in ENV_KEYS and v.strip()}
    if any("\n" in v or "\r" in v for v in updates.values()):
        raise ValueError("Keys can't contain line breaks.")
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    kept = [line for line in lines if line.partition("=")[0].strip() not in updates]
    path.write_text("\n".join([*kept, *(f"{k}={v}" for k, v in updates.items())]) + "\n")
    os.environ.update(updates)


def read_resume(path: Path) -> str:
    if not path.is_file():
        return ""
    if path.suffix.lower() == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages).strip()
    return path.read_text(encoding="utf-8").strip()


def background(ws: Workspace) -> str:
    profile = ws.profile.read_text(encoding="utf-8") if ws.profile.is_file() else ""
    resume = read_resume(ws.resume)
    return f"{profile}\n\nResume:\n{resume}" if resume else profile


def openai_client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("Add your OpenAI API key in Setup first.")
    return OpenAI(api_key=key)


def draft_id(listing: Listing) -> str:
    return hashlib.sha256(listing.key.encode()).hexdigest()[:16]


def refresh(ws: Workspace, web_query: str = "") -> tuple[int, int, list[str]]:
    """Pull every source, or search the web when given a query; returns new, total, errors."""
    config = ws.config()
    if web_query.strip():
        selected = search_jobs(openai_client(), config.model, web_query.strip())
        errors: list[str] = []
    else:
        incoming, errors = collect(config, date.today())
        selected = filter_items(incoming, config.keywords)
    before = load(ws.listings)
    all_items = merge(before, selected)
    save(ws.listings, all_items)
    return len(all_items) - len(before), len(all_items), errors


def make_draft(ws: Workspace, listing: Listing) -> StoredDraft:
    client = openai_client()
    model = ws.config().model
    draft = draft_message(client, model, background(ws), listing)
    fields = {
        **draft.model_dump(),
        "listing_url": str(listing.url),
        "listing_title": listing.title,
        "organization": listing.organization,
    }
    contact = find_contact(client, model, listing)
    if contact:
        fields |= {
            "recipient": contact[0].email,
            "recipient_source": contact[0].source_url,
            "recipient_verified": contact[1],
        }
    stored = StoredDraft.model_validate(fields)
    ws.drafts.mkdir(parents=True, exist_ok=True)
    out = ws.drafts / f"{draft_id(listing)}.json"
    out.write_text(json.dumps(stored.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return stored
