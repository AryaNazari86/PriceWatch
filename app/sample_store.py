"""State for the self-hosted sample product page used in the live demo.

Deliberately separate from the watchlist storage — this just models "a store
page whose price I can nudge with a button," not a tracked Product.
"""
from __future__ import annotations

import json
import os
import threading

from . import config

_lock = threading.Lock()

DEFAULT_PRODUCT = {
    "title": "Jean Paul Gaultier Le Male Elixir",
    "price": 249.00,
    "currency": "USD",
    "in_stock": True,
    "tagline": "Lavender & Tonka Bean",
}


def _load() -> dict:
    if not config.SAMPLE_PRODUCT_FILE.exists():
        return dict(DEFAULT_PRODUCT)
    try:
        return json.loads(config.SAMPLE_PRODUCT_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_PRODUCT)


def _save(data: dict) -> None:
    tmp_path = str(config.SAMPLE_PRODUCT_FILE) + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, config.SAMPLE_PRODUCT_FILE)


def get_sample_product() -> dict:
    with _lock:
        return _load()


def set_price(new_price: float) -> dict:
    with _lock:
        data = _load()
        data["price"] = round(new_price, 2)
        _save(data)
        return data


def reset() -> dict:
    with _lock:
        _save(dict(DEFAULT_PRODUCT))
        return dict(DEFAULT_PRODUCT)
