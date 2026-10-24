<div align="center">

# ↗ Intern Agent

**Find your next internship and email the team behind it, with your resume attached.**

A local web app that collects open roles from community internship lists, company job boards, the open web and developer conferences. It writes an email from your resume, finds a published hiring address, and sends from your Gmail when you click Send.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-8fd1b7?style=for-the-badge)](LICENSE)
[![Runs locally](https://img.shields.io/badge/runs-locally-10151e?style=for-the-badge)](#-privacy)

[**Quick start**](#-quick-start) · [**Where listings come from**](#-where-listings-come-from) · [**Sending email**](#-sending-email) · [**Privacy**](#-privacy)

</div>

---

## ✨ What it does

| | |
| --- | --- |
| 🔎 **Finds roles** | Every refresh reads the [SimplifyJobs](https://github.com/SimplifyJobs/Summer2027-Internships) and [vanshb03](https://github.com/vanshb03/Summer2027-Internships) internship lists, which track openings at thousands of companies. It also reads the Greenhouse, Lever and Ashby boards you follow and confs.tech conferences. You can search the web for anything else. |
| ✍️ **Writes the email** | Upload your resume once. Each draft uses only facts from your resume, your notes and the listing. |
| 📇 **Finds who to email** | Looks for a published recruiter or careers address. If the address appears on the cited page, it's marked **Published**. If not, it's marked **Unverified** and you have to tick a box confirming you checked it. |
| 📬 **Sends from your Gmail** | Edit the email, attach your resume, then click **Send email** twice to confirm. The same draft can't go to the same address twice by accident. |
| 🗂️ **Tracks it** | Drafted, Emailed, Applied and Skipped views keep your search in one place. |

## 🚀 Quick start

Requires **Python 3.12+**.

```bash
git clone https://github.com/aaravhmodi/agent-intern.git
cd agent-intern
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -e .
intern-agent
```

The app opens at `http://127.0.0.1:8766`. Everything else happens in the app:

1. **Setup → Resume:** upload your resume as a PDF.
2. **Setup → About you:** add what your resume doesn't say: the roles you want, locations, availability.
3. **Setup → Connections:** paste an [OpenAI API key](https://platform.openai.com/api-keys) for drafts and web search. Optionally, add your Gmail address and a [Google App Password](https://support.google.com/mail/answer/185833) to send.
4. **Refresh sources**, open a listing, and click **Write draft**.

## 🌐 Where listings come from

| Source | What it covers | Setup |
| --- | --- | --- |
| Community internship lists on GitHub | Active roles at thousands of companies, whatever system they hire through | None, always on |
| Greenhouse, Lever, Ashby boards | Every open role at the companies you follow | Add board names in Setup |
| Web search | Anything you describe, e.g. "backend intern Toronto winter 2027" | OpenAI key |
| [confs.tech](https://github.com/tech-conferences/conference-data) | Developer conferences and calls for speakers | Topics in Setup |

Use **Keywords** and **Only listings posted in the last … days** in Setup to narrow the results. Saved listings can go stale, so check the posting before you act on it.

## 📬 Sending email

- Gmail is used only when you click **Send email** and then click again to confirm. Nothing is sent automatically.
- Your resume is attached when **Attach resume** is ticked.
- An unverified address can't be sent to until you tick **I've checked this address is correct**.
- A draft can't go to the same address twice unless you choose **Send again**.
- Gmail needs [2-Step Verification](https://support.google.com/accounts/answer/185839) and an app password, not your normal password.

## 🔒 Privacy

- The app listens only on `127.0.0.1` and blocks requests from other sites.
- Your resume, notes, listings, drafts and keys stay in this folder (`resume.pdf`, `profile.md`, `data/`, `.env`), and Git ignores all of them.
- When you write a draft or search the web, the listing, your resume text and your notes are sent to OpenAI.
- Mail is sent through [Gmail SMTP over SSL](https://developers.google.com/workspace/gmail/imap/imap-smtp). The app never reads your inbox.

## ⌨️ Command line

```bash
intern-agent                       # open the app
intern-agent --port 9000 --no-browser
intern-agent search                # refresh every source, e.g. from cron
intern-agent search --web "ml intern remote"
```

## 🤝 Contributing

Issues and pull requests are welcome.

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## 📄 License

[MIT](LICENSE)
