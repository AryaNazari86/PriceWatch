"""Simple JSON-file persistence for the watchlist.

The watchlist is small (a handful of products for a demo) so a single JSON
file with an in-process threading.Lock is plenty — no need for a real
database for a 24-hour hackathon build. Writes are atomic (write to a temp
file, then rename) so a crash mid-write can't corrupt the file.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Optional

from . import config
from .models import Product

_lock = threading.Lock()
_products: dict[str, Product] = {}
_loaded = False


def _load_from_disk() -> dict[str, Product]:
    if not config.WATCHLIST_FILE.exists():
        return {}
    try:
        raw = json.loads(config.WATCHLIST_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {item["id"]: Product.model_validate(item) for item in raw}


def _save_to_disk(products: dict[str, Product]) -> None:
    tmp_path = str(config.WATCHLIST_FILE) + ".tmp"
    payload = [p.model_dump(mode="json") for p in products.values()]
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    os.replace(tmp_path, config.WATCHLIST_FILE)


def _ensure_loaded() -> None:
    global _loaded
    if not _loaded:
        _products.update(_load_from_disk())
        _loaded = True


def list_products() -> list[Product]:
    with _lock:
        _ensure_loaded()
        return list(_products.values())


def get_product(product_id: str) -> Optional[Product]:
    with _lock:
        _ensure_loaded()
        return _products.get(product_id)


def add_product(url: str) -> Product:
    with _lock:
        _ensure_loaded()
        product = Product(url=url)
        _products[product.id] = product
        _save_to_disk(_products)
        return product


def remove_product(product_id: str) -> bool:
    with _lock:
        _ensure_loaded()
        if product_id in _products:
            del _products[product_id]
            _save_to_disk(_products)
            return True
        return False


def save_product(product: Product) -> None:
    with _lock:
        _ensure_loaded()
        _products[product.id] = product
        _save_to_disk(_products)
