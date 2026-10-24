import os
from datetime import date
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest
from opportunity_lite import dashboard
from opportunity_lite.cli import _load_env
from opportunity_lite.leads.sending import SendRequest, StoredDraft, prepare_email
from opportunity_lite.models import Listing
from opportunity_lite.sources import conferences, greenhouse
from opportunity_lite.store import filter_items, merge
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
    newer = old.model_copy(update={"source": "b"})
    assert merge([old], [newer]) == [newer]
    assert filter_items([newer], ["engineer"]) == [newer]
    assert filter_items([newer], ["designer"]) == []


def test_send_requires_explicit_confirmation_and_blocks_duplicate() -> None:
    draft = StoredDraft(
        subject="A short question",
        email="Hello team,\nCould we talk?",
        short_message="Could we talk?",
        listing_url="https://example.org/job",
    )
    request = SendRequest(
        draft_id="0123456789abcdef", recipient="team@example.org", confirmed=True
    )
    message = prepare_email(request, draft, "me@example.org", already_sent=False)
    assert message["To"] == "team@example.org"
    with pytest.raises(ValueError, match="already sent"):
        prepare_email(request, draft, "me@example.org", already_sent=True)
    with pytest.raises(ValueError, match="Confirm"):
        prepare_email(
            request.model_copy(update={"confirmed": False}), draft, "me@example.org", False
        )


def test_dashboard_sends_only_after_click_and_blocks_repeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    draft_id = "0123456789abcdef"
    draft = StoredDraft(
        subject="A short question",
        email="Hello team,\nCould we talk?",
        short_message="Could we talk?",
        listing_url="https://example.org/job",
    )
    (drafts / f"{draft_id}.json").write_text(draft.model_dump_json(), encoding="utf-8")
    sent: list[str] = []
    monkeypatch.setattr(
        dashboard, "deliver", lambda message, sender, password: sent.append(str(message["To"]))
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.org")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-only")
    server = dashboard.create_server(tmp_path, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        with urlopen(url) as response:
            page = response.read().decode()
        assert sent == []
        csrf = page.split("name='csrf' value='")[1].split("'")[0]
        form = urlencode(
            {
                "csrf": csrf,
                "draft_id": draft_id,
                "recipient": "team@example.org",
                "confirmed": "yes",
            }
        ).encode()
        with urlopen(f"{url}/send", data=form) as response:
            assert response.status == 200
        assert sent == ["team@example.org"]
        with pytest.raises(HTTPError) as exc:
            urlopen(f"{url}/send", data=form)
        assert exc.value.code == 400
        assert sent == ["team@example.org"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
    _load_env(env)
    assert os.environ["OPENAI_API_KEY"] == "from-file"
    assert os.environ["GMAIL_ADDRESS"] == "shell@example.org"
    assert "GMAIL_APP_PASSWORD" not in os.environ
