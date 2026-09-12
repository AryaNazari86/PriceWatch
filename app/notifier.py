"""Email notification when a watched product's price changes.

Isolated behind one function — notify_price_change() — so it's a clean
no-op stub if RESEND_API_KEY / NOTIFY_EMAIL aren't configured, and a
one-file swap if you'd rather use a different provider later.

Sending is best-effort: a failed or unconfigured email must never break a
price check. Callers should treat this as fire-and-forget.
"""
from __future__ import annotations

import logging

import resend

from . import config
from .models import Product

logger = logging.getLogger(__name__)

_configured = False


def _ensure_configured() -> bool:
    global _configured
    if not config.RESEND_API_KEY or not config.NOTIFY_EMAIL:
        return False
    if not _configured:
        resend.api_key = config.RESEND_API_KEY
        _configured = True
    return True


def notify_price_change(product: Product, old_price: float, new_price: float, direction: str) -> None:
    """Send a best-effort email about a detected price change. Never raises."""
    if not _ensure_configured():
        logger.info(
            "Skipping email for %s (%s -> %s): RESEND_API_KEY/NOTIFY_EMAIL not set",
            product.title or product.url,
            old_price,
            new_price,
        )
        return

    verb = "dropped" if direction == "down" else "went up"
    arrow = "↓" if direction == "down" else "↑"
    subject = f"{arrow} {product.title or product.url} price {verb}: {old_price} → {new_price}"
    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 480px;">
      <h2 style="margin-bottom:4px;">Price {verb}</h2>
      <p style="color:#555;">{product.title or product.url}</p>
      <p style="font-size:1.4rem; margin: 12px 0;">
        <span style="text-decoration: line-through; color:#999;">{product.currency} {old_price}</span>
        &nbsp;&rarr;&nbsp;
        <strong>{product.currency} {new_price}</strong>
      </p>
      <p><a href="{product.url}">View product</a></p>
    </div>
    """

    try:
        resend.Emails.send(
            {
                "from": config.RESEND_FROM_EMAIL,
                "to": [config.NOTIFY_EMAIL],
                "subject": subject,
                "html": html,
            }
        )
        logger.info("Sent price-change email for %s", product.title or product.url)
    except Exception:  # noqa: BLE001 — a notification failure must not break the check
        logger.exception("Failed to send price-change email for %s", product.title or product.url)
