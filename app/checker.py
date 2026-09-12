"""Whole-watchlist check: run the single-product checker for every product
*in parallel* using a thread pool, then persist results and notify on change.

This is the headline feature: with N products, this fires up to
STEEL_MAX_CONCURRENCY real Steel cloud-browser sessions at once instead of
checking products one by one.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from . import config, storage
from .llm import ExtractedInfo
from .models import PricePoint, Product
from .notifier import notify_price_change
from .steel_checker import check_product_url

logger = logging.getLogger(__name__)


def _apply_result(product: Product, result: ExtractedInfo) -> Product:
    """Update `product` in place from a check result. Any price change vs.
    the previous check (up or down) is recorded on the product and a
    best-effort notification email is fired."""
    product.last_checked = datetime.now(timezone.utc)

    if result.error is not None or result.price is None:
        product.last_error = result.error or "Could not find a price on the page"
        product.last_change_direction = None
        product.last_change_amount = None
        return product

    previous_price = product.current_price  # None if this is the first successful check

    product.last_error = None
    product.title = result.title or product.title
    product.currency = result.currency or product.currency
    product.current_price = result.price
    product.in_stock = result.in_stock if result.in_stock is not None else product.in_stock
    product.price_history.append(
        PricePoint(
            price=result.price,
            currency=product.currency,
            in_stock=product.in_stock if product.in_stock is not None else True,
        )
    )

    if previous_price is not None and result.price != previous_price:
        direction = "down" if result.price < previous_price else "up"
        product.last_change_direction = direction
        product.last_change_amount = round(abs(result.price - previous_price), 2)
        notify_price_change(product, previous_price, result.price, direction)
    else:
        product.last_change_direction = None
        product.last_change_amount = None

    return product


def check_one_and_store(product_id: str) -> Product | None:
    """Check a single product (by id) and persist the update. Used for the
    "check it right after adding" UX touch, and reusable standalone."""
    product = storage.get_product(product_id)
    if product is None:
        return None
    result = check_product_url(product.url)
    product = _apply_result(product, result)
    storage.save_product(product)
    return product


def check_all_products() -> list[Product]:
    """Check every product on the watchlist in parallel and persist results.

    Returns the updated list of products.
    """
    products = storage.list_products()
    if not products:
        return []

    logger.info(
        "Checking %d product(s) in parallel (max %d at once)...",
        len(products),
        config.STEEL_MAX_CONCURRENCY,
    )

    updated: list[Product] = []
    with ThreadPoolExecutor(max_workers=config.STEEL_MAX_CONCURRENCY) as pool:
        future_to_product = {pool.submit(check_product_url, p.url): p for p in products}
        for future in as_completed(future_to_product):
            product = future_to_product[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 — one bad product must not sink the batch
                result = ExtractedInfo(title=None, price=None, currency=None, in_stock=None, error=str(exc))
            product = _apply_result(product, result)
            storage.save_product(product)
            updated.append(product)

    logger.info("Watchlist check complete.")
    return updated
