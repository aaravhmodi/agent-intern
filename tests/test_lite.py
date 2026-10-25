import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Thread
from unittest.mock import MagicMock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from opportunity_lite import dashboard, web
from opportunity_lite.leads.sending import SendRequest, StoredDraft, prepare_email
from opportunity_lite.models import Contact, Listing, WebPosting, WebPostings
from opportunity_lite.sources import ashby, conferences, github_list, greenhouse, lever
from opportunity_lite.store import filter_items, merge, save
from opportunity_lite.workspace import Workspace, draft_id, load_env, read_resume
from pydantic import ValidationError


def test_greenhouse_validates_and_keeps_source() -> None:
    listings = greenhouse(
        "sample",
        {
            "jobs": [
                {
                    "id": 17,
                    "title": "Platform Engineer",
                    "absolute_url": "https://boards.greenhouse.io/sample/jobs/17",
                    "location": {"name": "Remote"},
                    "content": "<p>Build reliable services &amp; APIs.</p>",
                }
            ]
        },
    )
    assert listings[0].description == "Build reliable services & APIs."
    assert listings[0].source == "Greenhouse: sample"
    with pytest.raises(ValidationError):
        greenhouse("sample", {"jobs": [{"id": 1, "title": "Missing URL"}]})


def test_conferences_filter_past_and_allow_blank_dates() -> None:
    items = conferences(
        "python",
        [
            {
                "name": "Upcoming",
                "url": "https://example.org/upcoming",
                "startDate": "2027-02-01",
                "endDate": "",
                "cfpEndDate": "",
            },
            {
                "name": "Past",
                "url": "https://example.org/past",
                "endDate": "2025-02-01",
            },
        ],
        date(2026, 10, 23),
    )
    assert [item.title for item in items] == ["Upcoming"]


def test_merge_and_keyword_filter() -> None:
    old = Listing(
        kind="job",
        title="Engineer",
        organization="Example",
        url="https://example.org/job",
        source="a",
    )
    newer = old.model_copy(update={"source": "b", "posted_on": date(2026, 10, 24)})
    assert merge([old], [newer]) == [newer]
    assert merge([old], [newer])[0].posted_on == date(2026, 10, 24)
    assert filter_items([newer], ["engineer"]) == [newer]
    assert filter_items([newer], ["designer"]) == []


def test_send_requires_explicit_confirmation_and_blocks_duplicate() -> None:
    draft = StoredDraft(
        subject="A short question",
        email="Hello team,\nCould we talk?",
        short_message="Could we talk?",
        listing_url="https://example.org/job",
    )
    request = SendRequest(draft_id="0123456789abcdef", recipient="team@example.org", confirmed=True)
    message = prepare_email(request, draft, "me@example.org", already_sent=False)
    assert message["To"] == "team@example.org"
    with pytest.raises(ValueError, match="already sent"):
        prepare_email(request, draft, "me@example.org", already_sent=True)
    with pytest.raises(ValueError, match="Confirm"):
        prepare_email(
            request.model_copy(update={"confirmed": False}), draft, "me@example.org", False
        )


def test_app_sends_with_resume_once_and_needs_unverified_address_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path)
    listing = Listing(
        kind="job",
        title="Backend Intern",
        organization="Sample Labs",
        url="https://example.org/job",
        source="Lever: sample",
    )
    save(ws.listings, [listing])
    key = draft_id(listing)
    ws.drafts.mkdir(parents=True)
    draft = StoredDraft(
        subject="A short question",
        email="Hello team,\nCould we talk?",
        short_message="Could we talk?",
        listing_url="https://example.org/job",
        recipient="team@example.org",
        recipient_source="https://example.org/contact",
    )
    (ws.drafts / f"{key}.json").write_text(draft.model_dump_json(), encoding="utf-8")
    ws.resume.write_bytes(b"%PDF-1.4 test")
    sent: list[str] = []
    monkeypatch.setattr(
        dashboard,
        "deliver",
        lambda message, sender, password: sent.extend(
            [str(message["To"]), *(p.get_filename() for p in message.iter_attachments())]
        ),
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.org")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-only")
    server = dashboard.create_server(ws, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"

    def post(path: str, body: dict[str, object], origin: str | None = None) -> int:
        headers = {"Content-Type": "application/json", **({"Origin": origin} if origin else {})}
        request = Request(f"{url}{path}", json.dumps(body).encode(), headers)
        try:
            with urlopen(request) as response:
                return int(response.status)
        except HTTPError as exc:
            return exc.code

    def listing_state() -> dict[str, object]:
        with urlopen(f"{url}/api/state") as response:
            return dict(json.load(response)["listings"][0])

    try:
        assert listing_state()["status"] == "drafted"
        send = {"key": key, "to": "team@example.org", "subject": "Hi", "body": "Hello"}
        assert post("/api/send", send) == 400  # suggested address not confirmed yet
        assert post("/api/send", {**send, "confirm_unverified": True}, "http://evil.test") == 403
        assert sent == []
        assert post("/api/send", {**send, "confirm_unverified": True}) == 200
        assert sent == ["team@example.org", "resume.pdf"]
        assert post("/api/send", {**send, "confirm_unverified": True}) == 400  # no repeat
        assert sent == ["team@example.org", "resume.pdf"]
        assert listing_state()["status"] == "emailed"
        assert post("/api/status", {"key": key, "status": "applied"}) == 200
        assert listing_state()["status"] == "applied"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_github_list_keeps_recent_open_rows_and_skips_bad_ones() -> None:
    today = date(2026, 10, 23)
    posted = int(datetime(2026, 10, 20, tzinfo=UTC).timestamp())
    old = int(datetime(2026, 8, 1, tzinfo=UTC).timestamp())
    row = {
        "company_name": "Sample Labs",
        "title": "Software Engineer Intern",
        "url": "https://example.org/jobs/1",
        "date_posted": posted,
        "active": True,
        "is_visible": True,
        "locations": ["Toronto, ON", "Remote"],
        "terms": ["Summer 2027"],
        "category": "Software",
    }
    rows = [
        row,
        {**row, "url": "https://example.org/jobs/closed", "active": False},
        {**row, "url": "https://example.org/jobs/old", "date_posted": old},
        {**row, "url": "not a url"},
        {**row, "url": "https://example.org/jobs/blank", "title": ""},
    ]
    listings = github_list("Owner/Repo", rows, today, max_age_days=30)
    assert [str(item.url) for item in listings] == ["https://example.org/jobs/1"]
    assert listings[0].location == "Toronto, ON; Remote"
    assert listings[0].description == "Summer 2027 · Software"
    assert listings[0].source == "GitHub: Owner/Repo"


def _client_returning(parsed: object) -> MagicMock:
    client = MagicMock()
    client.responses.parse.return_value.output_parsed = parsed
    return client


def test_web_search_keeps_only_valid_posting_urls() -> None:
    post = WebPosting(
        title="Backend Intern",
        organization="Sample Labs",
        url="https://example.org/careers/backend",
        location="Remote",
        description="Python services.",
    )
    client = _client_returning(
        WebPostings(postings=[post, post.model_copy(update={"url": "careers page"})])
    )
    listings = web.search_jobs(client, "model", "backend intern")
    assert [item.source for item in listings] == ["Web search"]
    assert client.responses.parse.call_args.kwargs["tools"] == [{"type": "web_search"}]


def test_contact_must_appear_on_its_source_page(monkeypatch: pytest.MonkeyPatch) -> None:
    listing = Listing(
        kind="job", title="Intern", organization="Sample", url="https://example.org/job", source="x"
    )
    client = _client_returning(
        Contact(email="Jobs@Example.org", source_url="https://example.org/contact")
    )
    monkeypatch.setattr(web, "published_on", lambda url, email: email == "jobs@example.org")
    found = web.find_contact(client, "model", listing)
    assert found is not None and found[0].email == "jobs@example.org" and found[1]
    monkeypatch.setattr(web, "published_on", lambda url, email: False)
    found = web.find_contact(client, "model", listing)
    assert found is not None and not found[1]
    client = _client_returning(Contact(email="", source_url=""))
    assert web.find_contact(client, "model", listing) is None
    monkeypatch.setattr(web, "published_on", lambda url, email: True)
    client = _client_returning(
        Contact(email="partners@example.org", source_url="https://example.org/contact")
    )
    assert web.find_contact(client, "model", listing) is None


def test_resume_is_read_and_attached(tmp_path: Path) -> None:
    resume = tmp_path / "resume.txt"
    resume.write_text("Built Python APIs.\n", encoding="utf-8")
    assert read_resume(resume) == "Built Python APIs."
    assert read_resume(tmp_path / "missing.pdf") == ""
    draft = StoredDraft(
        subject="Hi", email="Hello", short_message="Hi", listing_url="https://example.org/job"
    )
    request = SendRequest(draft_id="0123456789abcdef", recipient="a@example.org", confirmed=True)
    message = prepare_email(request, draft, "me@example.org", False, resume)
    files = [part.get_filename() for part in message.iter_attachments()]
    assert files == ["resume.txt"]


def test_env_file_fills_unset_values_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        '# comment\nOPENAI_API_KEY="from-file"\n'
        "GMAIL_ADDRESS=file@example.org\nGMAIL_APP_PASSWORD=\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GMAIL_ADDRESS", "shell@example.org")
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    load_env(env)
    assert os.environ["OPENAI_API_KEY"] == "from-file"
    assert os.environ["GMAIL_ADDRESS"] == "shell@example.org"
    assert "GMAIL_APP_PASSWORD" not in os.environ


def test_lever_and_ashby_boards_keep_dates_and_skip_unlisted() -> None:
    posted = int(datetime(2026, 10, 1, 12, tzinfo=UTC).timestamp() * 1000)
    jobs = lever(
        "kepler",
        [
            {
                "text": "Software Intern",
                "hostedUrl": "https://jobs.lever.co/kepler/1",
                "categories": {"location": "Toronto"},
                "createdAt": posted,
            }
        ],
    )
    assert (jobs[0].location, jobs[0].posted_on) == ("Toronto", date(2026, 10, 1))
    board = {
        "jobs": [
            {"title": "Intern", "jobUrl": "https://jobs.ashbyhq.com/a/1", "isListed": True},
            {"title": "Hidden", "jobUrl": "https://jobs.ashbyhq.com/a/2", "isListed": False},
        ]
    }
    assert [job.title for job in ashby("a", board)] == ["Intern"]
