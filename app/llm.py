"""LLM-based extraction of price/title/stock from arbitrary product page text.

Isolated behind a single function — extract_product_info() — so the provider
can be swapped by editing only this file. Default provider: Anthropic (a
fast/cheap model is plenty for this small, structured extraction task).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from anthropic import Anthropic

from . import config

_client: Optional[Anthropic] = None

MAX_PAGE_CHARS = 12000

SYSTEM_PROMPT = """You extract product listing data from the visible text of an \
e-commerce product page. The page may be from any store, in any layout or \
currency. Respond with ONLY a single JSON object, no prose, no markdown code \
fences. Shape exactly:

{"title": string or null, "price": number or null, "currency": string or null, "in_stock": boolean or null}

Rules:
- "price" is the current selling price as a plain number (no currency symbols, \
no thousands separators), e.g. 129.99. If there's a sale/discounted price and \
a crossed-out original price, use the sale price. If multiple variants/conditions \
are listed (e.g. "Open Box" vs "Refurbished"), use the first/primary listed price.
- "currency" is a 3-letter ISO code when you can tell (USD, EUR, GBP, ...), \
otherwise your best guess symbol as a string (e.g. "$"), otherwise null.
- "in_stock" is false only if the page clearly says out of stock / sold out / \
unavailable. Otherwise true.
- If you truly cannot find a price, set "price" to null.
"""


@dataclass
class ExtractedInfo:
    title: Optional[str]
    price: Optional[float]
    currency: Optional[str]
    in_stock: Optional[bool]
    error: Optional[str] = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _extract_json_object(text: str) -> dict:
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fall back to grabbing the first {...} blob in the response.
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"Could not find JSON object in LLM response: {text[:200]!r}")


def extract_product_info(page_text: str, url: str) -> ExtractedInfo:
    """Ask the LLM to pull structured product data out of raw page text.

    Safe to call from any thread — each call is independent and the
    underlying Anthropic client is thread-safe for concurrent requests.
    """
    trimmed = page_text[:MAX_PAGE_CHARS]
    try:
        client = _get_client()
        response = client.messages.create(
            model=config.LLM_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Product page URL: {url}\n\nPage text:\n{trimmed}",
                }
            ],
        )
        raw_text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        data = _extract_json_object(raw_text)
    except Exception as exc:  # noqa: BLE001 — surface any failure as a result, not a crash
        return ExtractedInfo(title=None, price=None, currency=None, in_stock=None, error=str(exc))

    price = data.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    return ExtractedInfo(
        title=data.get("title"),
        price=price,
        currency=data.get("currency"),
        in_stock=data.get("in_stock"),
    )
