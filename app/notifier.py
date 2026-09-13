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

    # Minimal, editorial layout in the same spirit as claude.ai's own
    # product surface: warm cream background, one accent color used
    # sparingly (the price + the single button), generous whitespace, no
    # colored badges/chips. Values duplicated from app/static/style.css
    # since email clients can't load CSS custom properties or a stylesheet.
    is_drop = direction == "down"
    accent_color = "#5f8d6a" if is_drop else "#a8433a"
    headline = "Price dropped" if is_drop else "Price increased"
    title = product.title or product.url

    html = f"""\
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@600&display=swap" rel="stylesheet" />
    </head>
    <body style="margin:0; padding:0; background-color:#f4efe6; font-family:'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4efe6;">
        <tr>
          <td align="center" style="padding:56px 24px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:460px;">
              <tr>
                <td style="padding-bottom:40px;">
                  <span style="font-weight:700; font-size:0.95rem; color:#1c1a17; letter-spacing:-0.01em;">PriceWatch</span>
                </td>
              </tr>
              <tr>
                <td style="padding-bottom:6px;">
                  <h1 style="margin:0; font-size:1.6rem; font-weight:600; letter-spacing:-0.02em; color:#1c1a17;">{headline}</h1>
                </td>
              </tr>
              <tr>
                <td style="padding-bottom:28px;">
                  <p style="margin:0; font-size:0.98rem; color:#6b6152; line-height:1.5;">{title}</p>
                </td>
              </tr>
              <tr>
                <td style="padding-bottom:36px; border-top:1px solid #d6c7a8; border-bottom:1px solid #d6c7a8; padding-top:24px; padding-bottom:24px;">
                  <span style="font-family:'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:0.95rem; color:#8a7f6c; text-decoration:line-through;">{product.currency} {old_price:.2f}</span>
                  <span style="color:#8a7f6c; padding:0 8px;">&rarr;</span>
                  <span style="font-family:'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:1.5rem; font-weight:600; color:{accent_color};">{product.currency} {new_price:.2f}</span>
                </td>
              </tr>
              <tr>
                <td style="padding-top:32px;">
                  <a href="{product.url}" style="display:inline-block; background-color:#cc785c; color:#f4efe6; font-weight:600; font-size:0.92rem; text-decoration:none; padding:13px 26px; border-radius:10px;">View product</a>
                </td>
              </tr>
              <tr>
                <td style="padding-top:48px;">
                  <p style="margin:0; font-size:0.8rem; color:#8a7f6c;">You're getting this because this product is on your PriceWatch watchlist.</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
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
