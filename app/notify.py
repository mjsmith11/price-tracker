import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger("price_tracker.notify")


def send_price_drop_email(*, item_name: str, store: str, price: float, threshold: float,
                           currency: str, product_url: str) -> bool:
    if not (settings.smtp_host and settings.email_from and settings.email_to):
        logger.warning("SMTP not configured; skipping email for %s", item_name)
        return False

    msg = EmailMessage()
    msg["Subject"] = f"Price drop: {item_name} is now {currency} {price:.2f}"
    msg["From"] = settings.email_from
    msg["To"] = settings.email_to
    msg.set_content(
        f"{item_name} dropped to {currency} {price:.2f} at {store} "
        f"(your threshold was {currency} {threshold:.2f}).\n\n{product_url}"
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_pass)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("failed to send price drop email for %s", item_name)
        return False
