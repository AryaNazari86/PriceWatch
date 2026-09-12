"""Single-product check: real cloud browser (Steel) + Playwright + LLM extraction.

Flow (per the Steel Python docs/cookbook — see examples/playwright-py in
https://github.com/steel-dev/steel-cookbook):
  1. Create a Steel session (Steel client).
  2. Connect Playwright to it over CDP using session.websocket_url + api key.
  3. Navigate to the product URL and grab the visible page text.
  4. Always release the Steel session, even on failure.
  5. Hand the text to the LLM extraction module.

Uses Playwright's *sync* API. Per Playwright's own docs, the sync API is not
thread-safe globally, but each thread may create and use its own
sync_playwright() instance — which is exactly what this function does, so
it's safe to run many of these concurrently via a ThreadPoolExecutor (see
checker.py).
"""
from __future__ import annotations

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from steel import Steel

from . import config
from .llm import ExtractedInfo, extract_product_info


def fetch_page_text(url: str) -> str:
    """Open `url` in a fresh Steel cloud browser session and return its visible text."""
    client = Steel(steel_api_key=config.STEEL_API_KEY)
    session = client.sessions.create()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(
                f"{session.websocket_url}&apiKey={config.STEEL_API_KEY}"
            )
            try:
                # Steel sessions come with a context already attached.
                context = browser.contexts[0]
                page = context.new_page()
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=config.PAGE_NAV_TIMEOUT_MS,
                )
                # Many stores render price via a client-side widget after the
                # shell loads. Give the network a chance to go quiet (catches
                # that async fetch) but don't block forever on pages with
                # chatty analytics/polling that never fully idle.
                try:
                    page.wait_for_load_state("networkidle", timeout=6000)
                except PlaywrightTimeoutError:
                    pass
                # Final settle buffer for any last render pass.
                page.wait_for_timeout(1500)
                return page.inner_text("body")
            finally:
                browser.close()
    finally:
        client.sessions.release(session.id)


def check_product_url(url: str) -> ExtractedInfo:
    """Full single-product check: fetch the page via Steel, then extract via LLM.

    Safe to call from a worker thread.
    """
    try:
        page_text = fetch_page_text(url)
    except Exception as exc:  # noqa: BLE001 — network/session errors become a result
        return ExtractedInfo(title=None, price=None, currency=None, in_stock=None, error=str(exc))
    return extract_product_info(page_text, url)
