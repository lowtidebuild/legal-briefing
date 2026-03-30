from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_briefing_email(
    html_body: str,
    subject: str,
    smtp_user: str,
    smtp_pass: str,
    recipients: list[str],
) -> None:
    """Send the rendered briefing email through Gmail SMTP using BCC-style delivery."""
    if not recipients:
        logger.info("No recipients configured, skipping email delivery")
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = smtp_user
    # Keep recipient addresses out of visible headers. Actual delivery targets
    # are provided to SMTP separately via ``to_addrs`` below.
    message["To"] = smtp_user
    message.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_pass)
        server.send_message(message, from_addr=smtp_user, to_addrs=recipients)

    logger.info("Sent briefing email to %d recipients", len(recipients))
