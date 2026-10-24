"""Gmail transport, called only from the dashboard after sending checks."""

import smtplib
from email.message import EmailMessage


def deliver(message: EmailMessage, sender: str, app_password: str) -> None:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)
