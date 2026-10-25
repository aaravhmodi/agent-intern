# Intern Agent walkthrough

[Watch the MP4](media/walkthrough.mp4) · [Animated preview](media/demo.gif)

The silent video uses the actual local web app in Chromium, with the same chapter-card
format as the original demo. It covers resume upload, background and settings, GitHub
internship lists, a Lever board, conferences, web search, drafting, contact verification,
and tracking. The final send confirmation is never clicked and no email is sent.

Alex Morgan and the employers are fictional. HTTP feeds, contact-page content and
structured AI responses are fixtures; validation, source parsing, PDF extraction,
settings persistence, drafting orchestration and rendering run normally. No credentials
or paid API calls are needed. “Published” in this recording refers to the fixture page.

## Try it yourself

Run `intern-agent`, then open **Resume & settings** to upload your PDF, write your
background and configure connections. **Refresh sources** reads the internship lists
and your chosen boards/topics. **From the web** searches for the query you enter.
Select a listing and choose **Write draft**, then review the address, subject and body.
Sending requires your Gmail connection and a second confirmation click.

Older saved listings may have no posted date. Refresh updates the date when the same
listing is returned by a source with a date; unavailable listings and sources that
provide no date will still show a dash.

## Reproduce the recording

From this repository on a Linux Docker host:

```bash
docker build -t intern-agent-demo -f scripts/demo/Dockerfile .
mkdir -p docs/media
docker run --rm --network none --shm-size=512m \
  -e DEMO_OUTPUT=/output -v "$PWD/docs/media:/output" intern-agent-demo
```

Only the output directory is mounted. The build downloads dependencies; the recording
runs without external networking. SMTP is disabled at both the app and transport
boundaries. The recorder asserts that it never requests `/api/send`.

The recorder temporarily replaces `frame-ancestors 'none'` in its own process with
the exact localhost presentation origin. The installed app's CSP remains unchanged.
Every run uses a fresh temporary workspace and placeholder connection values.

Outputs include `walkthrough.mp4`, `demo.gif`, `poster.png`, `review.png`, and mobile
screenshots at 390px and 320px. Intermediate WebM files and raw recordings are ignored.

## Browser regression check

Use the same fixtures and assertions without video capture or presentation pauses:

```bash
docker run --rm --network none --shm-size=512m \
  -e DEMO_OUTPUT=/output -v "$PWD/docs/media:/output" \
  intern-agent-demo python scripts/demo/record.py --check
```

For local development, install the app and `playwright==1.55.0`, run
`python -m playwright install chromium`, then `python scripts/demo/record.py --check`.
Recording locally also needs FFmpeg on PATH. `DEMO_CHROMIUM` optionally selects a
Chromium executable; otherwise the recorder uses system Chromium or Playwright's browser.

Checks cover resume upload/extraction, saved settings and masked connection fields,
source views, text filtering, web search, both contact badges, draft attachments,
send-button arming, tracking transitions, mobile overflow and closing mobile detail.
Live provider availability and actual Gmail delivery are outside this fixture check.
