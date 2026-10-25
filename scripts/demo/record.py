"""Exercise and record the real app with fictional feeds and disabled transports."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import MagicMock, patch

from fixtures import contact_page, feed, parse, resume
from opportunity_lite import dashboard
from opportunity_lite.workspace import ENV_KEYS, Workspace, read_resume
from playwright.sync_api import Page, expect, sync_playwright


def exercise(page: Page, url: str, work: Path, output: Path, check: bool) -> None:
    frame = page.frame_locator("#browser")

    def chapter(label: str, title: str, subtitle: str, index: int) -> None:
        page.evaluate("args => window.chapter(...args)", [label, title, subtitle, index])

    def hold(seconds: float = 3) -> None:
        if not check:
            page.wait_for_timeout(seconds * 1000)

    def view(name: str) -> None:
        frame.locator(f'[data-view="{name}"]').click()

    def save(selector: str, endpoint: str) -> None:
        with page.expect_response(
            lambda r: r.url.endswith(endpoint) and r.request.method == "POST"
        ) as response:
            frame.locator(selector).click()
        assert response.value.ok, endpoint
        # Wait for the subsequent state reload to finish rendering.
        if selector.startswith("[data-status"):
            expect(frame.locator(selector)).to_have_count(0)
        else:
            expect(frame.locator(selector)).to_be_enabled()

    page.evaluate("window.mode('browser')")
    page.locator("#browser").evaluate("(el, url) => el.src=url", url)
    expect(frame.locator("#view-title")).to_have_text("All listings")
    chapter(
        "01 / MAKE IT YOURS",
        "Your search starts here.",
        "One local web app. Upload a resume and choose what matters to you.",
        0,
    )
    view("setup")
    resume(work / "sample.pdf")
    frame.locator("#resume-file").set_input_files(work / "sample.pdf")
    save("#resume-up", "/api/resume")
    expect(frame.locator(".setup")).to_contain_text("characters read for drafts")
    assert "Alex Morgan" in read_resume(work / "resume.pdf")
    hold()
    frame.locator("#profile").fill(
        "Alex Morgan, software engineering student. Built Python APIs and a PostgreSQL "
        "project tracker. Looking for a winter 2027 internship."
    )
    save("#profile-save", "/api/profile")
    frame.locator("#c-keywords").fill("intern, summit")
    frame.locator("#c-age").fill("45")
    frame.locator("#c-lever").fill("samplelabs")
    frame.locator("#c-topics").fill("python")
    save("#config-save", "/api/config")
    hold()
    frame.locator("#k-openai").fill("demo-placeholder-not-a-key")
    frame.locator("#k-gmail").fill("alex@example.org")
    frame.locator("#k-pass").fill("demo-placeholder-not-a-password")
    save("#keys-save", "/api/keys")
    expect(frame.locator("#k-openai")).to_have_value("")
    expect(frame.locator("#k-pass")).to_have_value("")
    view("all")
    view("setup")
    expect(frame.locator("#c-age")).to_have_value("45")
    expect(frame.locator("#c-lever")).to_have_value("samplelabs")
    expect(frame.locator("#profile")).to_contain_text("Alex Morgan")
    assert json.loads((work / "config.json").read_text())["max_age_days"] == 45
    chapter(
        "02 / DISCOVER",
        "A wider search. One place to review.",
        "GitHub internship lists, company boards, and conferences. Fictional feeds; real app.",
        1,
    )
    view("all")
    save("#find", "/api/refresh")
    expect(frame.locator(".row")).to_have_count(3)
    hold(4)
    page.screenshot(path=str(output / "poster.png"))
    view("lists")
    expect(frame.locator(".row")).to_have_count(2)
    hold()
    frame.locator("#q").fill("Northstar")
    expect(frame.locator(".row")).to_have_count(1)
    frame.locator("#q").fill("")
    view("boards")
    expect(frame.locator(".row")).to_have_count(1)
    hold()
    view("conferences")
    expect(frame.locator(".row")).to_have_count(1)
    hold()
    view("web")
    frame.locator("#q").fill("backend intern remote winter 2027")
    save("#find", "/api/refresh")
    expect(frame.locator(".row")).to_have_count(1)
    hold(4)
    chapter(
        "03 / WRITE A DRAFT",
        "Start with your experience.",
        "The app uses your resume and background. AI responses are fixtures in this demo.",
        2,
    )
    view("lists")
    frame.locator(".row").filter(has_text="Sample Labs").click()
    save("[data-draft]", "/api/draft")
    expect(frame.locator("#detail")).to_contain_text("Published")
    expect(frame.locator("#f-attach")).to_be_checked()
    hold(5)
    chapter(
        "04 / REVIEW",
        "Your words. Your decision.",
        "Review the address, edit the message, and keep the resume attached. No email is sent.",
        3,
    )
    frame.locator("#f-subject").fill("Winter internship - Python API experience")
    frame.locator("#f-body").scroll_into_view_if_needed()
    hold(4)
    page.screenshot(path=str(output / "review.png"))
    # First click only arms the UI; never issue a send request.
    frame.locator("#send").click()
    expect(frame.locator("#send")).to_have_text("Click again to send")
    hold(2)
    view("drafted")
    expect(frame.locator(".row")).to_have_count(1)
    view("web")
    frame.locator(".row").click()
    save("[data-draft]", "/api/draft")
    expect(frame.locator("#detail")).to_contain_text("Unverified")
    expect(frame.locator("#f-verified")).not_to_be_checked()
    chapter(
        "CHECK THE SOURCE",
        "A suggested address needs checking.",
        "Published means the address appears on the cited page. Unverified needs your review.",
        3,
    )
    hold(4)
    frame.locator("#f-verified").check()
    save('[data-status="skipped"]', "/api/status")
    view("skipped")
    expect(frame.locator(".row")).to_have_count(1)
    frame.locator(".row").click()
    save('[data-status="new"]', "/api/status")
    view("boards")
    frame.locator(".row").click()
    save('[data-status="applied"]', "/api/status")
    view("applied")
    expect(frame.locator(".row")).to_have_count(1)
    view("emailed")
    expect(frame.locator(".row")).to_have_count(0)
    chapter(
        "READY WHEN YOU ARE",
        "Small, local, and open source.",
        "Run intern-agent to begin. github.com/aaravhmodi/agent-intern",
        3,
    )
    view("all")
    hold(4)


def mobile(page: Page, url: str, output: Path) -> None:
    for width in (390, 320):
        page.set_viewport_size({"width": width, "height": 844})
        page.goto(url)
        page.locator('[data-view="setup"]').click()
        expect(page.locator("#profile")).to_contain_text("Alex Morgan")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
            f"Setup overflows at {width}px"
        )
        page.screenshot(path=str(output / f"mobile-setup-{width}.png"), full_page=True)
        page.locator('[data-view="all"]').click()
        page.locator(".row").first.click()
        expect(page.locator("#aside")).to_be_visible()
        page.locator("#close").click()
        expect(page.locator("#aside")).not_to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(output / f"mobile-list-{width}.png"), full_page=True)


def record(check: bool) -> None:
    output = Path(os.environ.get("DEMO_OUTPUT", "docs/media")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    client = MagicMock()
    client.responses.parse.side_effect = parse
    with tempfile.TemporaryDirectory(prefix="intern-agent-demo-") as temp, patch.dict(os.environ):
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        work = Path(temp)
        app = dashboard.create_server(Workspace(work), 0)
        stage = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            partial(SimpleHTTPRequestHandler, directory=str(Path(__file__).parent)),
        )
        url = f"http://127.0.0.1:{app.server_port}/"
        stage_origin = f"http://127.0.0.1:{stage.server_port}"
        # Only the recorder permits embedding, and only from its own stage origin.
        csp = dashboard.CSP.replace("frame-ancestors 'none'", f"frame-ancestors {stage_origin}")
        errors: list[str] = []
        sends: list[str] = []
        threads = [Thread(target=s.serve_forever, daemon=True) for s in (app, stage)]
        with (
            patch("opportunity_lite.sources.fetch_json", side_effect=feed),
            patch("opportunity_lite.workspace.openai_client", return_value=client),
            patch("opportunity_lite.web.urlopen", side_effect=contact_page),
            patch(
                "opportunity_lite.dashboard.deliver",
                side_effect=AssertionError("Demo mail disabled"),
            ) as mail,
            patch("smtplib.SMTP_SSL", side_effect=AssertionError("Demo SMTP disabled")),
            patch.object(dashboard, "CSP", csp),
            sync_playwright() as pw,
        ):
            for thread in threads:
                thread.start()
            try:
                executable = os.environ.get("DEMO_CHROMIUM") or shutil.which("chromium")
                browser = pw.chromium.launch(executable_path=executable, args=["--no-sandbox"])
                options = (
                    {}
                    if check
                    else {
                        "record_video_dir": str(output / "raw"),
                        "record_video_size": {"width": 1440, "height": 900},
                    }
                )
                context = browser.new_context(viewport={"width": 1440, "height": 900}, **options)
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith((url, stage_origin + "/"))
                        else route.abort()
                    ),
                )
                page = context.new_page()
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.on(
                    "request",
                    lambda req: sends.append(req.url) if req.url.endswith("/api/send") else None,
                )
                page.goto(stage_origin + "/stage.html")
                exercise(page, url, work, output, check)
                video = page.video
                context.close()
                if video:
                    video.save_as(str(output / "walkthrough.webm"))
                mobile_context = browser.new_context()
                mobile_page = mobile_context.new_page()
                mobile_page.on("pageerror", lambda err: errors.append(str(err)))
                mobile(mobile_page, url, output)
                mobile_context.close()
                browser.close()
                assert not errors, errors
                assert not sends, "Recording must not submit email"
                mail.assert_not_called()
                print(
                    "Browser checks passed: setup, PDF, sources, web search, draft, "
                    "contact badges, tracking, mobile. No email sent."
                )
            finally:
                for server in (app, stage):
                    server.shutdown()
                    server.server_close()
                for thread in threads:
                    thread.join(timeout=2)
    if not check:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(output / "walkthrough.webm"),
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
                str(output / "walkthrough.mp4"),
            ],
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(output / "walkthrough.mp4"),
                "-filter_complex",
                "[0:v]setpts=0.65*PTS,fps=8,scale=880:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3",
                "-loop",
                "0",
                str(output / "demo.gif"),
            ],
            check=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Run browser assertions without recording"
    )
    record(parser.parse_args().check)
