"""Local web app: one page and a small JSON API. Email goes out only from a click on it."""

import json
import os
import webbrowser
from datetime import UTC, datetime
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from opportunity_lite.leads.sending import SendRequest, StoredDraft, is_email, prepare_email
from opportunity_lite.mailer import deliver
from opportunity_lite.models import Config, Listing
from opportunity_lite.store import load
from opportunity_lite.workspace import (
    ENV_KEYS,
    Workspace,
    draft_id,
    make_draft,
    read_resume,
    refresh,
    save_env,
)

_MAP = TypeAdapter(dict[str, str])
_STATIC = files("opportunity_lite") / "static"
_LOCAL_HOSTS = {"127.0.0.1", "localhost"}
MAX_BODY = 200_000
MAX_RESUME = 10_000_000
CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "frame-ancestors 'none'"
)


class KeyRequest(BaseModel):
    key: str = Field(pattern=r"^[0-9a-f]{16}$")


class StatusRequest(KeyRequest):
    status: Literal["applied", "skipped", "new"]


class SendBody(KeyRequest):
    to: str
    subject: str
    body: str
    attach_resume: bool = True
    confirm_unverified: bool = False
    resend: bool = False


class RefreshRequest(BaseModel):
    web: str = Field(default="", max_length=300)


class ProfileRequest(BaseModel):
    text: str = Field(max_length=20_000)


class KeysRequest(BaseModel):
    OPENAI_API_KEY: str = ""
    GMAIL_ADDRESS: str = ""
    GMAIL_APP_PASSWORD: str = ""


def _read_map(path: Path) -> dict[str, str]:
    return _MAP.validate_json(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _write_map(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@lru_cache(maxsize=4)
def _resume_chars(path: str, mtime: float) -> int:
    try:
        return len(read_resume(Path(path)))
    except Exception:  # a scanned or damaged PDF still attaches; it just has no text
        return 0


def _drafts(ws: Workspace) -> dict[str, StoredDraft]:
    found: dict[str, StoredDraft] = {}
    for path in ws.drafts.glob("*.json") if ws.drafts.is_dir() else []:
        try:
            found[path.stem] = StoredDraft.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            continue
    return found


def _marks(ws: Workspace) -> Path:
    return ws.root / "data" / "status.json"


def state(ws: Workspace) -> dict[str, Any]:
    drafts, sent, marks = _drafts(ws), _read_map(ws.sent), _read_map(_marks(ws))
    last_sent: dict[str, tuple[str, str]] = {}
    for sent_key, at in sent.items():
        key, _, to = sent_key.partition(":")
        if key not in last_sent or at > last_sent[key][1]:
            last_sent[key] = (to, at)

    def view(item: Listing) -> dict[str, Any]:
        key, draft = draft_id(item), drafts.get(draft_id(item))
        to, at = last_sent.get(key, (None, None))
        status = marks.get(key) or ("emailed" if at else "drafted" if draft else "new")
        return {
            **item.model_dump(mode="json"),
            "description": item.description[:1500],
            "key": key,
            "status": status,
            "draft": draft.model_dump(mode="json") if draft else None,
            "sent_to": to,
            "sent_at": at,
        }

    items = sorted(
        load(ws.listings),
        key=lambda i: (i.posted_on is None, -(i.posted_on or datetime.min).toordinal()),
    )
    resume = None
    if ws.resume.is_file():
        stat = ws.resume.stat()
        resume = {
            "name": ws.resume.name,
            "size": stat.st_size,
            "chars": _resume_chars(str(ws.resume), stat.st_mtime),
        }
    gmail = os.environ.get("GMAIL_ADDRESS", "")
    return {
        "listings": [view(item) for item in items],
        "sender": gmail if gmail and os.environ.get("GMAIL_APP_PASSWORD") else None,
        "keys": {key: bool(os.environ.get(key)) for key in ENV_KEYS},
        "gmail_address": gmail,
        "resume": resume,
        "profile": ws.profile.read_text(encoding="utf-8") if ws.profile.is_file() else "",
        "config": ws.config().model_dump(),
        "updated": (
            datetime.fromtimestamp(ws.listings.stat().st_mtime, UTC).isoformat()
            if ws.listings.is_file()
            else None
        ),
    }


def _send(ws: Workspace, body: SendBody, lock: Lock) -> None:
    path = ws.drafts / f"{body.key}.json"
    saved = StoredDraft.model_validate_json(path.read_text(encoding="utf-8"))
    draft = StoredDraft.model_validate(
        {**saved.model_dump(mode="json"), "subject": body.subject, "email": body.body}
    )
    unverified = body.to.strip().lower() == draft.recipient and not draft.recipient_verified
    request = SendRequest(
        draft_id=body.key,
        recipient=body.to,
        confirmed=body.confirm_unverified or not unverified,
    )
    sender = os.environ.get("GMAIL_ADDRESS", "").strip().lower()
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not sender or not password:
        raise ValueError("Connect Gmail in Setup to send email.")
    with lock:
        sent = _read_map(ws.sent)
        sent_key = f"{request.draft_id}:{request.recipient}"
        resume = ws.resume if body.attach_resume and ws.resume.is_file() else None
        message = prepare_email(
            request, draft, sender, sent_key in sent and not body.resend, resume
        )
        path.write_text(json.dumps(draft.model_dump(mode="json"), indent=2) + "\n", "utf-8")
        deliver(message, sender, password)
        sent[sent_key] = datetime.now(UTC).isoformat()
        _write_map(ws.sent, sent)


def _listing(ws: Workspace, key: str) -> Listing:
    for item in load(ws.listings):
        if draft_id(item) == key:
            return item
    raise ValueError("That listing is no longer saved. Refresh and try again.")


def _message(exc: ValidationError) -> str:
    return str(exc.errors()[0]["msg"]).removeprefix("Value error, ")


def create_server(ws: Workspace, port: int) -> ThreadingHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535.")
    lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send_bytes(self, status: HTTPStatus, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: HTTPStatus, data: Any) -> None:
            self._send_bytes(status, json.dumps(data).encode(), "application/json")

        def _allowed(self) -> bool:
            """Block DNS rebinding and cross-site requests: this server can send email."""
            if self.headers.get("Host", "").rsplit(":", 1)[0] not in _LOCAL_HOSTS:
                return False
            origin = self.headers.get("Origin")
            return (
                self.command == "GET"
                or origin is None
                or (urlsplit(origin).hostname in _LOCAL_HOSTS)
            )

        def do_GET(self) -> None:
            if not self._allowed():
                return self._json(HTTPStatus.FORBIDDEN, {"detail": "Forbidden"})
            path = urlsplit(self.path).path
            if path == "/":
                page = (_STATIC / "index.html").read_bytes()
                return self._send_bytes(HTTPStatus.OK, page, "text/html; charset=utf-8")
            if path == "/dashboard.css":
                css = (_STATIC / "dashboard.css").read_bytes()
                return self._send_bytes(HTTPStatus.OK, css, "text/css; charset=utf-8")
            if path == "/api/state":
                return self._json(HTTPStatus.OK, state(ws))
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

        def do_POST(self) -> None:
            if not self._allowed():
                return self._json(HTTPStatus.FORBIDDEN, {"detail": "Cross-site request blocked"})
            path = urlsplit(self.path).path
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            limit = MAX_RESUME if path == "/api/resume" else MAX_BODY
            if not 0 <= length <= limit:
                return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"detail": "Too large"})
            raw = self.rfile.read(length)
            try:
                if path == "/api/resume":
                    if self.headers.get("Content-Type") != "application/pdf":
                        raise ValueError("Upload your resume as a PDF.")
                    if not raw.startswith(b"%PDF"):
                        raise ValueError("That file isn't a PDF.")
                    ws.resume.write_bytes(raw)
                    return self._json(HTTPStatus.OK, {"ok": True})
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Expected JSON.")
                payload = json.loads(raw or b"{}")
                result = self._route(path, payload)
            except (ValueError, ValidationError, OSError) as exc:
                text = _message(exc) if isinstance(exc, ValidationError) else str(exc)
                return self._json(HTTPStatus.BAD_REQUEST, {"detail": text})
            except LookupError:
                return self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            except Exception as exc:  # OpenAI, network, or Gmail failures
                failed = "Gmail did not confirm the send" if path == "/api/send" else "Failed"
                detail = f"{failed}: {type(exc).__name__}."
                return self._json(HTTPStatus.BAD_GATEWAY, {"detail": detail})
            self._json(HTTPStatus.OK, result)

        def _route(self, path: str, payload: Any) -> dict[str, Any]:
            if path == "/api/refresh":
                new, total, errors = refresh(ws, RefreshRequest.model_validate(payload).web)
                return {"added": new, "total": total, "errors": errors}
            if path == "/api/draft":
                make_draft(ws, _listing(ws, KeyRequest.model_validate(payload).key))
                return {"ok": True}
            if path == "/api/send":
                _send(ws, SendBody.model_validate(payload), lock)
                return {"ok": True}
            if path == "/api/status":
                update = StatusRequest.model_validate(payload)
                with lock:
                    marks = _read_map(_marks(ws))
                    if update.status == "new":
                        marks.pop(update.key, None)
                    else:
                        marks[update.key] = update.status
                    _write_map(_marks(ws), marks)
                return {"ok": True}
            if path == "/api/profile":
                ws.profile.write_text(ProfileRequest.model_validate(payload).text, "utf-8")
                return {"ok": True}
            if path == "/api/config":
                ws.save_config(Config.model_validate(payload))
                return {"ok": True}
            if path == "/api/keys":
                keys = KeysRequest.model_validate(payload)
                if keys.GMAIL_ADDRESS.strip() and not is_email(keys.GMAIL_ADDRESS.strip()):
                    raise ValueError("Enter a valid Gmail address.")
                save_env(ws.env, keys.model_dump())
                return {"ok": True}
            raise LookupError(path)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(ws: Workspace, port: int, open_browser: bool = True) -> None:
    server = create_server(ws, port)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Intern Agent is running at {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
