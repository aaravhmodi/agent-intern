# Intern Agent walkthrough

[Watch the full MP4](media/walkthrough.mp4) · [Animated preview](media/demo.gif)

The video was screen-recorded in Chromium on a Linux server. The terminal panels display output from the real CLI, and the review panel is the actual local dashboard. The surrounding titles and chapter cards are presentation graphics.

Sample Labs, Alex Morgan, and Developer Summit are fictional. Public feed responses and the AI response are fixtures so the recording is repeatable, uses no credentials, and makes no paid API calls. Gmail transport is disabled in the recording, and the Send button is never clicked. The video is silent with on-screen chapter captions.

## Follow along with your own data

1. Follow the [setup guide](../README.md#setup), then choose company board tokens and conference topics in `config.json`.
2. Put your real skills and experience in `profile.md`. Keep it factual; the app uses this text when drafting.
3. Run `intern-agent search` to fetch the configured public feeds and validate their results. Run `intern-agent list` to see saved listings and their source links. `intern-agent list --query engineer` filters the view.
4. Set `OPENAI_API_KEY` and run `intern-agent draft NUMBER`, using a number from the full, unfiltered list. The selected listing and your profile are sent to OpenAI; the draft is saved locally.
5. Run `intern-agent dashboard` and open `http://127.0.0.1:8766`. Read the email and short message. You can copy either into your usual messaging app.
6. To send through Gmail, follow the [optional Gmail setup](../README.md#optional-gmail-sending). Restart the dashboard from the terminal with those environment variables set. Enter a verified recipient, review the content, check the confirmation, and click **Send one email**.

On Windows, use `.\.venv\Scripts\intern-agent.exe` in place of `intern-agent` unless you activated the virtual environment.

The app currently searches configured Greenhouse boards and confs.tech conference feeds. It does not search every employer or every type of event. Saved results can become stale, so check each original listing before contacting anyone.

## Reproduce the recording

From the repository root on a Linux machine with Docker:

```bash
docker build -t intern-agent-demo -f scripts/demo/Dockerfile .
mkdir -p docs/media
docker run --rm --network none --shm-size=512m \
  -v "$PWD/docs/media:/output" intern-agent-demo
```

The build installs the recording tools. The recording itself runs with networking disabled and no host credentials or browser profiles mounted. It writes `walkthrough.mp4`, `demo.gif`, and two stills to `docs/media`; intermediate WebM recordings are ignored by Git. The container exits and stops its temporary local servers after recording.
