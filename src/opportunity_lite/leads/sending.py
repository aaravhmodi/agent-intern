"""Pure checks for one reviewed, explicitly requested email send."""

import mimetypes
import re
from email.message import EmailMessage
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from opportunity_lite.models import Draft

_EMAIL = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[A-Za-z]{2,}$")


def is_email(value: str) -> bool:
    return bool(_EMAIL.fullmatch(value))


class StoredDraft(Draft):
    listing_url: HttpUrl
    listing_title: str = ""
    organization: str = ""
    recipient: str = ""
    recipient_source: HttpUrl | None = None
    recipient_verified: bool = False


class SendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    recipient: str
    confirmed: bool

    @field_validator("recipient")
    @classmethod
    def valid_email(cls, value: str) -> str:
        address = value.strip().lower()
        if not _EMAIL.fullmatch(address):
            raise ValueError("Enter one valid recipient email address.")
        return address


def prepare_email(
    request: SendRequest,
    draft: StoredDraft,
    sender: str,
    already_sent: bool,
    resume: Path | None = None,
) -> EmailMessage:
    if not request.confirmed:
        raise ValueError("Confirm that you checked the recipient address.")
    if already_sent:
        raise ValueError("This draft was already sent to that address.")
    if not _EMAIL.fullmatch(sender):
        raise ValueError("Configure a valid GMAIL_ADDRESS first.")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = request.recipient
    message["Subject"] = draft.subject
    message.set_content(draft.email)
    if resume is not None:
        kind = mimetypes.guess_type(resume.name)[0] or "application/octet-stream"
        maintype, subtype = kind.split("/", 1)
        message.add_attachment(
            resume.read_bytes(), maintype=maintype, subtype=subtype, filename=resume.name
        )
    return message
