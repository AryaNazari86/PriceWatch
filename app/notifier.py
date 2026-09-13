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

    # Same palette and type system as app/static/style.css (values duplicated
    # here, not shared, since email clients can't load CSS custom properties
    # or the site's stylesheet). Sans font matches the site (Plus Jakarta
    # Sans, loaded where the email client allows web fonts, falling back to
    # the system stack elsewhere); prices use the same monospace as the
    # dashboard's numerals.
    is_drop = direction == "down"
    status_color = "#5f8d6a" if is_drop else "#a8433a"
    status_bg = "rgba(95, 141, 106, 0.14)" if is_drop else "rgba(168, 67, 58, 0.14)"
    status_label = "PRICE DROPPED" if is_drop else "PRICE INCREASED"
    title = product.title or product.url

    html = f"""\
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=JetBrains+Mono:wght@600&display=swap" rel="stylesheet" />
    </head>
    <body style="margin:0; padding:32px 16px; background-color:#f4efe6; font-family:'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px; margin:0 auto; background-color:#ece3d3; border:1px solid #d6c7a8; border-radius:18px;">
        <tr>
          <td style="padding:28px 32px 8px;">
            <span style="display:inline-flex; align-items:center; gap:8px; font-weight:800; font-size:1.05rem; color:#1c1a17; letter-spacing:-0.01em;">
              <span style="color:#cc785c; font-size:1.2rem; line-height:1;">&#8986;</span> PriceWatch
            </span>
          </td>
        </tr>
        <tr>
          <td style="padding:12px 32px 0;">
            <span style="display:inline-block; font-size:0.7rem; font-weight:700; letter-spacing:0.06em; color:{status_color}; background-color:{status_bg}; border-radius:999px; padding:5px 12px;">
              {status_label}
            </span>
          </td>
        </tr>
        <tr>
          <td style="padding:14px 32px 0;">
            <p style="margin:0; font-size:1.05rem; font-weight:600; color:#1c1a17; line-height:1.4;">{title}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 32px 4px;">
            <span style="font-family:'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:0.95rem; color:#8a7f6c; text-decoration:line-through;">{product.currency} {old_price:.2f}</span>
            <span style="color:#8a7f6c; padding:0 6px;">&rarr;</span>
            <span style="font-family:'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:1.4rem; font-weight:700; color:{status_color};">{product.currency} {new_price:.2f}</span>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 32px 32px;">
            <a href="{product.url}" style="display:inline-block; background-color:#cc785c; color:#f4efe6; font-weight:700; font-size:0.9rem; text-decoration:none; padding:12px 22px; border-radius:999px;">View product</a>
          </td>
        </tr>
      </table>
      <p style="max-width:480px; margin:16px auto 0; padding:0 32px; font-size:0.78rem; color:#8a7f6c; text-align:center;">
        You're getting this because this product is on your PriceWatch watchlist.
      </p>
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
