# PriceWatch

PriceWatch watches product prices for you. Add a product by URL — that's
it, no target price to set. A backend agent opens the page in a real cloud
browser (via [Steel](https://steel.dev)), reads the current price off
whatever layout the store happens to use (via an LLM), and compares it to
the last time it checked. Any change — up or down — gets flagged on the
dashboard and emailed to you. The whole watchlist is re-checked every 24
hours — **in parallel**, one Steel session per product — with a live "watch
face" countdown to the next check and a manual refresh button.

Includes a self-hosted sample product page with a price-change control, so
you can demo the full loop end-to-end: change the price, hit refresh, watch
PriceWatch catch it — on the dashboard and in your inbox.

## Stack

- **Flask** (Python, sync) — see below for why, and how parallel checks still work without async.
- **Playwright** (sync API) driving a **Steel** cloud browser session per product check.
- **Anthropic** (`claude-haiku-4-5`) to extract `{title, price, currency, in_stock}` as strict JSON from arbitrary page text — isolated in [`app/llm.py`](app/llm.py) so the provider/model is a one-file swap. Cost is negligible for this workload: roughly 1,500–2,500 input tokens and ~50 output tokens per product check (~$0.002–0.003/check at Haiku 4.5 rates), so even heavy hackathon testing stays well under $1–2 total.
- **Resend** to email a notification whenever a price change is detected — isolated in [`app/notifier.py`](app/notifier.py); it's a clean no-op if `RESEND_API_KEY`/`NOTIFY_EMAIL` aren't set, so the rest of the app works without it.
- JSON-file storage for the watchlist (`data/watchlist.json`) — persists across restarts, no database needed for this scope.
- A background `threading.Thread` owns the 24-hour auto-check loop and the "next check" timestamp; the dashboard polls `/api/state` and renders a countdown from that timestamp, so a page reload never resets the clock.
- Server-rendered dashboard (Flask + Jinja2) with vanilla JS polling — no frontend build step.

### How parallel checks work in a sync framework

The core feature — checking every watchlist product against Steel at once —
doesn't need `asyncio` to be real. `app/checker.py` fans the whole watchlist
out across a `concurrent.futures.ThreadPoolExecutor` (size set by
`STEEL_MAX_CONCURRENCY`), and each worker thread creates and drives its own
`sync_playwright()` instance — which is exactly the pattern Playwright's own
docs describe for using the sync API from multiple threads. Steel's sync
client and the Anthropic SDK are both safe to call concurrently from separate
threads too. So N products really do get checked against N live Steel
sessions at the same time.

### How price-change detection works

Each product stores its full price history. After every check, the new price
is compared to the price from the *previous* check:

- Different (either direction) → the product is flagged `dropped` or
  `increased` on the dashboard for that check, and `notify_price_change()`
  fires a best-effort email via Resend.
- Same → no flag, no email.
- The product's all-time lowest price is tracked separately and shown as a
  `lowest` badge regardless of whether this specific check changed anything.

## Setup

```bash
./setup.sh
```

This creates a virtualenv, installs dependencies, installs the Playwright
Chromium browser binary, and copies `.env.example` to `.env`. **Edit `.env`**
and fill in:

- `STEEL_API_KEY` — from [app.steel.dev](https://app.steel.dev/settings/api-keys)
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com)
- `RESEND_API_KEY` and `NOTIFY_EMAIL` — sign up free at [resend.com](https://resend.com), then create a key at [resend.com/api-keys](https://resend.com/api-keys). Without these, the app still works fully — you just won't get emails, only the on-screen dashboard alert.

## Run

```bash
./run.sh
```

Then open **http://127.0.0.1:8000**.

## Demoing the live price-change flow

Steel sessions run in the cloud, so they can't reach `127.0.0.1` on your
laptop directly. To let the cloud browser see your local sample page during
a demo, expose it with a tunnel (e.g. `ngrok http 8000`) and use the
resulting public URL instead of `127.0.0.1` when adding the sample product.

1. Start a tunnel: `ngrok http 8000` (or any tunnel tool you have) and copy
   the `https://...ngrok...` URL it prints.
2. On the dashboard, add `<that-ngrok-url>/sample` to the watchlist.
3. Open `<that-ngrok-url>/sample` in another tab — it has a small "PriceWatch
   demo controls" box at the bottom, separate from the fake store page above it.
4. Change the price (or click "−$50 (trigger a drop)").
5. Back on the dashboard, click **Refresh now**. The card should flip to a
   pulsing **Price dropped!** state within a few seconds, and (if Resend is
   configured) an email should land shortly after.

## Notes / non-goals

- No auth, single shared watchlist — matches the hackathon scope. `NOTIFY_EMAIL` is one global address, not per-user.
- No deployment — runs on `localhost` only.
- The 24-hour schedule is in-memory only; it doesn't need to survive a
  process restart (per spec) — on restart it just starts a fresh 24h countdown.
- Email is best-effort and non-blocking: if Resend isn't configured or a send
  fails, the check still completes and the dashboard still shows the change.
