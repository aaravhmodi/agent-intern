# Intern Agent

A small local tool for finding jobs and opportunities from public sources, then generating messages to review. Gmail sending is optional and happens only when you click **Send one email** on the local draft page. The tool does not submit applications or send emails automatically.

## Setup

Requires Python 3.12 or newer. On Windows PowerShell:

```powershell
git clone https://github.com/aaravhmodi/agent-intern.git
Set-Location agent-intern
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item config.example.json config.json
Copy-Item profile.example.md profile.md
```

On macOS or Linux:

```bash
git clone https://github.com/aaravhmodi/agent-intern.git
cd agent-intern
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp config.example.json config.json
cp profile.example.md profile.md
```

On Windows, use `.\.venv\Scripts\intern-agent.exe` wherever the commands below say `intern-agent`. Add the [Greenhouse board tokens](https://support.greenhouse.io/hc/en-us/articles/5888210160155-Find-your-job-board-URL) for companies you want to follow to `greenhouse_boards` in `config.json`. For example, a board URL ending in `/example` has token `example`. The sample configuration has no boards, so add at least one to find jobs. `conference_topics` are topic filenames in the [confs.tech data repository](https://github.com/tech-conferences/conference-data); `keywords` optionally filters both jobs and events. Empty keywords keep everything.

Write your own factual background in `profile.md`. That file and `config.json` are ignored by Git. Create an [OpenAI API key](https://platform.openai.com/api-keys) and set `OPENAI_API_KEY` in your shell only when you want to generate a draft. The model is configurable in `config.json`.

```powershell
# PowerShell, for the current terminal only
$env:OPENAI_API_KEY = "your-key-here"
```

```bash
# macOS/Linux, for the current terminal only
export OPENAI_API_KEY="your-key-here"
```

```bash
intern-agent search
intern-agent list
intern-agent list --query engineer
intern-agent draft 1
intern-agent dashboard
```

Open `http://127.0.0.1:8766` to review drafts. Search saves validated listings to `data/listings.json`. Each item keeps its public source URL. Drafts go to `data/drafts/`. Listing numbers come from the full `list` command, not a filtered view. The app keeps older saved listings even if a later source refresh fails; check the original page before acting. To focus on internships, add words such as `intern` or `co-op` to `keywords`. Empty keywords show jobs of any level.

## Optional Gmail sending

You can use search and drafts without Gmail. To send from the local dashboard:

1. Turn on [2-Step Verification](https://support.google.com/accounts/answer/185839) for the Gmail account and create a [Google App Password](https://support.google.com/mail/answer/185833). Some work, school, and Advanced Protection accounts may not offer app passwords.
2. Set your Gmail address and the app password in the terminal where you start the dashboard. Use the app password, not your normal Google password. Do not put either value in `config.json` or commit it to Git.
3. Run `intern-agent dashboard`, open `http://127.0.0.1:8766`, review a draft, enter a recipient address, check the confirmation box, and click **Send one email**. The app prevents sending the same draft to the same address twice.

```powershell
# PowerShell, for the current terminal only
$env:GMAIL_ADDRESS = "you@gmail.com"
$env:GMAIL_APP_PASSWORD = "your-app-password"
intern-agent dashboard
```

```bash
# macOS/Linux, for the current terminal only
export GMAIL_ADDRESS="you@gmail.com"
export GMAIL_APP_PASSWORD="your-app-password"
intern-agent dashboard
```

The dashboard listens only on your computer (`127.0.0.1`). It sends through [Gmail SMTP over SSL on port 465](https://developers.google.com/workspace/gmail/imap/imap-smtp). The app stores the time of each confirmed send in local `data/sent.json`; it does not read your Gmail inbox. If Gmail is unavailable, you can still copy a draft into Gmail manually.

## Sources and privacy

- [Greenhouse Job Board API](https://docs.greenhouse.io/job-board) publishes job posts through unauthenticated GET requests. You choose which company boards to search.
- [confs.tech conference-data](https://github.com/tech-conferences/conference-data) provides public JSON grouped by year and topic.
- Profile, search results, drafts, and sent records stay in local ignored files. Draft generation sends the selected listing and your profile to the configured OpenAI model. See [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## License

MIT. See [LICENSE](LICENSE).
