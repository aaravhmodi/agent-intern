"""Local-only review page with one explicit Send button per draft."""

import html
import json
import os
import secrets
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs

from pydantic import TypeAdapter, ValidationError

from opportunity_lite.leads.sending import SendRequest, StoredDraft, prepare_email
from opportunity_lite.mailer import deliver

_SENT = TypeAdapter(dict[str, str])


def _page(data_dir: Path, csrf: str, notice: str = "") -> str:
    cards: list[str] = []
    for path in sorted((data_dir / "drafts").glob("*.json")):
        if len(path.stem) != 16 or any(c not in "0123456789abcdef" for c in path.stem):
            continue
        try:
            draft = StoredDraft.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            continue
        safe_id = html.escape(path.stem)
        cards.append(
            "<article>"
            f"<h2>{html.escape(draft.subject)}</h2>"
            f"<p><a href='{html.escape(str(draft.listing_url), quote=True)}' "
            "target='_blank' rel='noopener'>Original listing</a></p>"
            f"<pre>{html.escape(draft.email)}</pre>"
            f"<p><strong>Short message:</strong> {html.escape(draft.short_message)}</p>"
            "<form method='post' action='/send'>"
            f"<input type='hidden' name='csrf' value='{csrf}'>"
            f"<input type='hidden' name='draft_id' value='{safe_id}'>"
            "<label>Recipient email <input name='recipient' type='email' required></label>"
            "<label><input type='checkbox' name='confirmed' value='yes' required> "
            "I checked this recipient address and reviewed this draft.</label>"
            "<button type='submit'>Send one email</button></form></article>"
        )
    body = "".join(cards) or "<p>No drafts yet. Run <code>intern-agent draft NUMBER</code>.</p>"
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Intern Agent drafts</title>"
        "<style>body{font:16px system-ui;max-width:800px;margin:2rem auto;padding:0 1rem}"
        "article{border:1px solid #ccc;border-radius:8px;padding:1rem;margin:1rem 0}"
        "pre{white-space:pre-wrap;font:inherit;background:#f5f5f5;padding:1rem}"
        "label{display:block;margin:.7rem 0}button{padding:.5rem 1rem}</style>"
        f"<h1>Intern Agent drafts</h1><p role='status'>{html.escape(notice)}</p>{body}</html>"
    )


def create_server(data_dir: Path, port: int) -> ThreadingHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535.")
    csrf = secrets.token_urlsafe(32)
    lock = Lock()
    sent_path = data_dir / "sent.json"

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: HTTPStatus, notice: str = "") -> None:
            body = _page(data_dir, csrf, notice).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'"
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _local_host(self) -> bool:
            return self.headers.get("Host", "").split(":")[0] in {"127.0.0.1", "localhost"}

        def do_GET(self) -> None:
            if not self._local_host() or self.path != "/":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._reply(HTTPStatus.OK)

        def do_POST(self) -> None:
            if not self._local_host() or self.path != "/send":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if int(self.headers.get("Content-Length", "0")) > 4096:
                self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            fields = parse_qs(self.rfile.read(length).decode())
            if fields.get("csrf") != [csrf]:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            try:
                request = SendRequest(
                    draft_id=fields.get("draft_id", [""])[0],
                    recipient=fields.get("recipient", [""])[0],
                    confirmed=fields.get("confirmed") == ["yes"],
                )
                draft_path = data_dir / "drafts" / f"{request.draft_id}.json"
                draft = StoredDraft.model_validate_json(draft_path.read_text(encoding="utf-8"))
                sender = os.environ.get("GMAIL_ADDRESS", "").strip().lower()
                password = os.environ.get("GMAIL_APP_PASSWORD", "")
                if not password:
                    raise ValueError("Set GMAIL_APP_PASSWORD to enable Gmail sending.")
                with lock:
                    sent = (
                        _SENT.validate_json(sent_path.read_text(encoding="utf-8"))
                        if sent_path.exists()
                        else {}
                    )
                    sent_key = f"{request.draft_id}:{request.recipient}"
                    message = prepare_email(request, draft, sender, sent_key in sent)
                    deliver(message, sender, password)
                    sent[sent_key] = datetime.now(UTC).isoformat()
                    sent_path.parent.mkdir(parents=True, exist_ok=True)
                    sent_path.write_text(json.dumps(sent, indent=2) + "\n", encoding="utf-8")
            except (OSError, ValueError, ValidationError) as exc:
                self._reply(HTTPStatus.BAD_REQUEST, str(exc))
                return
            except Exception:
                self._reply(HTTPStatus.BAD_GATEWAY, "Gmail did not confirm the send.")
                return
            self._reply(HTTPStatus.OK, f"Sent one email to {request.recipient}.")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(data_dir: Path, port: int) -> None:
    server = create_server(data_dir, port)
    print(f"Review drafts at http://127.0.0.1:{server.server_port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
