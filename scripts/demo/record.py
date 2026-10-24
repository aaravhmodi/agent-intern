"""Record real CLI output and the real dashboard with deterministic public fixtures.

The presentation frame is video artwork. App behavior comes from the installed package.
HTTP feed and AI response boundaries are mocked; SMTP is disabled at the transport boundary.
"""

# Presentation copy and embedded HTML intentionally keep long lines.
# ruff: noqa: E501

import contextlib
import io
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from unittest.mock import MagicMock, patch

from opportunity_lite.cli import main
from opportunity_lite.dashboard import create_server
from opportunity_lite.models import Draft
from playwright.sync_api import Page, sync_playwright

OUTPUT = Path(os.environ.get("DEMO_OUTPUT", "/output"))
WORK = Path("/tmp/intern-agent-demo")


def fixture_feed(url: str) -> Any:
    if "greenhouse.io" in url:
        return {
            "jobs": [
                {
                    "id": 1,
                    "title": "Software Engineer Intern",
                    "absolute_url": "https://example.org/jobs/software",
                    "location": {"name": "Remote"},
                    "content": "Build Python APIs and reliable product features with a small engineering team.",
                },
                {
                    "id": 2,
                    "title": "Data Engineer",
                    "absolute_url": "https://example.org/jobs/data",
                    "location": {"name": "Toronto, Canada"},
                    "content": "Build data pipelines and improve PostgreSQL reliability.",
                },
            ]
        }
    return [
        {
            "name": "Developer Summit",
            "url": "https://example.org/summit",
            "startDate": str(date.today() + timedelta(days=40)),
            "endDate": str(date.today() + timedelta(days=41)),
            "city": "Toronto",
            "country": "Canada",
            "cfpUrl": "https://example.org/summit/speak",
            "cfpEndDate": str(date.today() + timedelta(days=15)),
        }
    ]


def run_cli(*args: str) -> str:
    client = MagicMock()
    client.responses.parse.return_value.output_parsed = Draft(
        subject="Software engineering internship — Python API experience",
        email="Hi Sample Labs team,\n\nI’m Alex, a software engineering student who has built Python APIs and a PostgreSQL-backed project tracker. Your internship’s focus on reliable product features caught my interest.\n\nWould you be open to a brief chat about the role and how I could contribute?\n\nThanks,\nAlex",
        short_message="Hi Sample Labs team — I’m Alex, a student with Python API and PostgreSQL experience. Could we chat briefly about your software engineering internship?",
    )
    output = io.StringIO()
    with (
        patch.object(sys, "argv", ["intern-agent", *args]),
        patch("opportunity_lite.sources.fetch_json", side_effect=fixture_feed),
        patch("opportunity_lite.cli.OpenAI", return_value=client),
        patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-only-not-a-key"}),
        contextlib.redirect_stdout(output),
    ):
        main()
    return output.getvalue().rstrip()


def chapter(page: Page, label: str, title: str, subtitle: str, index: int) -> None:
    page.evaluate("args => window.chapter(...args)", [label, title, subtitle, index])


def terminal(page: Page, command: str, output: str, hold: int = 5500) -> None:
    page.evaluate("window.mode('terminal')")
    page.evaluate("window.command('')")
    for index in range(1, len(command) + 1):
        page.evaluate("s => document.querySelector('#typed').textContent=s", command[:index])
        page.wait_for_timeout(32)
    page.wait_for_timeout(450)
    page.evaluate("s => window.output(s)", output)
    page.wait_for_timeout(hold)


def record() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    os.chdir(WORK)
    Path("config.json").write_text(
        json.dumps(
            {
                "greenhouse_boards": ["samplelabs"],
                "conference_topics": ["python"],
                "keywords": [],
                "model": "gpt-4o-mini",
            }
        ),
        encoding="utf-8",
    )
    Path("profile.md").write_text(
        "Alex Morgan, software engineering student. Built Python APIs and a PostgreSQL-backed project tracker. Interested in internships and developer events.",
        encoding="utf-8",
    )
    search = run_cli("search")
    listings = run_cli("list")
    drafting = run_cli("draft", "3")
    # No mail transport can run in this recording, even if an accidental click occurs.
    os.environ.pop("GMAIL_ADDRESS", None)
    os.environ.pop("GMAIL_APP_PASSWORD", None)
    app = create_server(WORK / "data", 0)
    stage = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(SimpleHTTPRequestHandler, directory=str(Path(__file__).resolve().parent)),
    )
    for server in (app, stage):
        Thread(target=server.serve_forever, daemon=True).start()
    try:
        with (
            patch(
                "opportunity_lite.dashboard.deliver",
                side_effect=RuntimeError("Demo transport disabled"),
            ),
            sync_playwright() as playwright,
        ):
            browser = playwright.chromium.launch(
                executable_path="/usr/bin/chromium", args=["--no-sandbox"]
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                record_video_dir=str(OUTPUT / "raw"),
                record_video_size={"width": 1440, "height": 900},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{stage.server_port}/stage.html")
            chapter(
                page,
                "MEET INTERN AGENT",
                "Find your next role. And what comes after.",
                "Public job boards, developer opportunities, and messages you can make your own.",
                0,
            )
            page.evaluate("window.mode('hero')")
            page.locator("#hero").evaluate(
                "el => el.innerHTML = `<h2>A smaller search stack.<br><em>A clearer next step.</em></h2><div class='tiles'><div class='tile'><b>Discover</b><p>Jobs from Greenhouse.<br>Events from confs.tech.</p></div><div class='tile'><b>Draft</b><p>Your background, one listing,<br>a message to review.</p></div><div class='tile'><b>Send, optionally</b><p>Connect Gmail.<br>You choose when to send.</p></div></div>`"
            )
            page.wait_for_timeout(5000)
            page.screenshot(path=str(OUTPUT / "poster.png"))
            chapter(
                page,
                "01 / MAKE IT YOURS",
                "Your search starts with your preferences.",
                "Choose public company boards and topics. Add your own background in profile.md.",
                0,
            )
            terminal(
                page,
                "cat config.json",
                '{\n  "greenhouse_boards": ["samplelabs"],\n  "conference_topics": ["python"],\n  "keywords": [],\n  "model": "gpt-4o-mini"\n}',
                5000,
            )
            chapter(
                page,
                "02 / DISCOVER",
                "One refresh. Jobs and opportunities.",
                "This recording uses fictional source fixtures; the search and validation code is real.",
                1,
            )
            terminal(page, "intern-agent search", search, 3000)
            terminal(page, "intern-agent list", listings, 6500)
            chapter(
                page,
                "03 / START THE CONVERSATION",
                "Turn a relevant role into a first draft.",
                "Uses your profile and the selected listing. AI output is a fixture in this demo.",
                2,
            )
            terminal(page, "intern-agent draft 3", drafting, 3500)
            chapter(
                page,
                "04 / REVIEW",
                "Read it in your own time.",
                "The actual local dashboard: review the email and the shorter message before using either.",
                3,
            )
            page.evaluate("window.mode('browser')")
            page.locator("#browser").evaluate(
                "(el, url) => el.src=url", f"http://127.0.0.1:{app.server_port}/"
            )
            frame = page.frame_locator("#browser")
            frame.get_by_role("heading", name="Intern Agent drafts").wait_for()
            page.wait_for_timeout(6000)
            frame.locator("input[name=recipient]").scroll_into_view_if_needed()
            page.wait_for_timeout(1800)
            frame.locator("input[name=recipient]").press_sequentially("team@example.org", delay=100)
            page.wait_for_timeout(1500)
            frame.locator("input[name=confirmed]").check()
            chapter(
                page,
                "OPTIONAL / GMAIL",
                "Sending stays in your hands.",
                "Connect Gmail with an app password, verify the recipient, then click Send one email.",
                3,
            )
            page.wait_for_timeout(5000)
            page.screenshot(path=str(OUTPUT / "review.png"))
            chapter(
                page,
                "READY WHEN YOU ARE",
                "Small, local, and open source.",
                "Start with search. Add AI drafts and optional Gmail when you need them.",
                3,
            )
            page.evaluate("window.mode('hero')")
            page.locator("#hero").evaluate(
                "el => el.innerHTML=`<h2>Your next opportunity<br><em>starts with a better search.</em></h2><p class='sub'>github.com/aaravhmodi/agent-intern</p><div class='tiles'><div class='tile'><b>MIT licensed</b><p>Run it. Adapt it. Contribute.</p></div><div class='tile'><b>Local files</b><p>Your profile and drafts stay with you.<br>AI drafting uses OpenAI.</p></div><div class='tile'><b>Optional Gmail</b><p>One reviewed message per click.<br>No email was sent in this demo.</p></div></div>`"
            )
            page.wait_for_timeout(5500)
            video = page.video
            context.close()
            assert video is not None
            video.save_as(str(OUTPUT / "walkthrough.webm"))
            browser.close()
    finally:
        for server in (app, stage):
            server.shutdown()
            server.server_close()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(OUTPUT / "walkthrough.webm"),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(OUTPUT / "walkthrough.mp4"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(OUTPUT / "walkthrough.mp4"),
            "-filter_complex",
            "[0:v]setpts=0.65*PTS,fps=8,scale=880:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3",
            "-loop",
            "0",
            str(OUTPUT / "demo.gif"),
        ],
        check=True,
    )


if __name__ == "__main__":
    record()
