"""PriceWatch — Flask app.

Routes:
  GET  /                     dashboard (initial render; JS polls /api/state)
  GET  /api/state            watchlist + summary + scheduler countdown, as JSON
  POST /api/products         add a product {url}
  DELETE /api/products/<id>  remove a product
  POST /api/refresh          trigger an immediate whole-watchlist check

  GET  /sample                self-hosted demo product page
  POST /sample/price           set the demo page's price (form post)
  POST /sample/reset           reset the demo page to its default price
"""
from __future__ import annotations

import logging

from flask import Flask, jsonify, redirect, render_template, request, url_for

from . import config, sample_store, storage
from .scheduler import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = Flask(__name__)


def _summary(products) -> dict:
    total_price = sum(p.current_price for p in products if p.current_price is not None)
    return {
        "total_current_price": round(total_price, 2),
        "item_count": len(products),
    }


def _full_state() -> dict:
    products = storage.list_products()
    products.sort(key=lambda p: p.created_at)
    return {
        "products": [p.public_dict() for p in products],
        "summary": _summary(products),
        "scheduler": scheduler.state(),
    }


@app.route("/")
def dashboard():
    return render_template("dashboard.html", state=_full_state())


@app.route("/api/state")
def api_state():
    return jsonify(_full_state())


@app.route("/api/products", methods=["POST"])
def api_add_product():
    payload = request.get_json(silent=True) or request.form
    url = (payload.get("url") or "").strip()

    if not url:
        return jsonify({"error": "url is required"}), 400

    storage.add_product(url=url)

    # Adding a product triggers the same full-watchlist refresh as clicking
    # "Refresh now" — it checks the new item immediately (along with
    # everything else already on the list) and resets the countdown, rather
    # than quietly checking just the new product in the background.
    scheduler.trigger_now()

    return jsonify(_full_state()), 201


@app.route("/api/products/<product_id>", methods=["DELETE"])
def api_remove_product(product_id: str):
    removed = storage.remove_product(product_id)
    if not removed:
        return jsonify({"error": "not found"}), 404
    return jsonify(_full_state())


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    scheduler.trigger_now()
    return jsonify(_full_state())


@app.route("/sample")
def sample_page():
    return render_template("sample.html", product=sample_store.get_sample_product())


@app.route("/sample/price", methods=["POST"])
def sample_set_price():
    try:
        price = float(request.form.get("price", ""))
    except (TypeError, ValueError):
        price = None
    if price is not None and price >= 0:
        sample_store.set_price(price)
    return redirect(url_for("sample_page"))


@app.route("/sample/reset", methods=["POST"])
def sample_reset():
    sample_store.reset()
    return redirect(url_for("sample_page"))


if __name__ == "__main__":
    scheduler.start()
    app.run(host=config.HOST, port=config.PORT, debug=False)
