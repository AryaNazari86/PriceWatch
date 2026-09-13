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
out across a `concurrent.futures.ThreadPoolExecutor` sized to the watchlist
itself (one worker per product, no artificial cap), and each worker thread
creates and drives its own `sync_playwright()` instance — which is exactly
the pattern Playwright's own docs describe for using the sync API from
multiple threads. Steel's sync client and the Anthropic SDK are both safe to
call concurrently from separate threads too. So N products really do get
checked against N live Steel sessions at the same time.

One consequence: the per-page wait time in `app/steel_checker.py`
(`NETWORK_IDLE_TIMEOUT_MS` / `PAGE_SETTLE_MS` — how long it lets a page's
network go quiet before reading its text, needed because many stores render
price via a client-side widget after the page shell loads) is essentially
free at the batch level. It's paid once per batch, concurrently, not once
per product — checking 10 products with a 10s wait takes about the same
wall-clock time as checking 1, not 10x. That's why these are tuned generous
rather than tight.

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

## Demoing the live price-change flow (for judges)

Steel sessions run in the cloud, so they can't reach `127.0.0.1` on your
laptop directly. Expose your local server with a tunnel and use the public
URL instead of `127.0.0.1` when adding the sample product.

**Setup (do this once, before judges are watching):**

1. In a spare terminal: `ngrok http 8000` — copy the `https://<random>.ngrok-free.app`
   URL it prints. (Keep this terminal open for the whole demo — closing it kills the tunnel.)
   - Free-tier ngrok shows a "you're visiting a tunnel" interstitial to first-time
     browser visitors. That's already handled: `app/steel_checker.py` sends the
     `ngrok-skip-browser-warning` header on every fetch, so Steel scrapes the real
     page, not the warning screen. This only affects our own scraper — if *you*
     open the ngrok URL in your own browser, you'll still see that interstitial
     once; just click through it.
2. On the dashboard, add `<ngrok-url>/sample` to the watchlist and confirm it
   comes back with a real title/price (not an error) — this proves the tunnel
   and Steel can both reach it, before you're on stage.
3. Open `<ngrok-url>/sample` in another tab and click through the ngrok
   interstitial once (see above). You should land on the "Aether Automatic
   Chronograph" page with the demo controls box at the bottom.

**The live demo:**

1. Point at the dashboard — the countdown ring, summary stats, watchlist.
2. Switch to the sample-page tab, click **"−$50 (trigger a drop)"**.
3. Switch back to the dashboard, click **Refresh now**.
4. Within a few seconds the card flips to a pulsing **Price dropped!** state
   with the new price and the amount it dropped by; if Resend is configured,
   an email lands shortly after — worth having your inbox open on a second
   screen/tab as a payoff beat.

**Backup plan:** if ngrok has any hiccup live (rate limits, a stale tunnel
URL, wifi issues), `cloudflared tunnel --url http://localhost:8000` (`brew
install cloudflared`) is a solid fallback — it has no interstitial at all,
so it needs no special header handling. Test whichever one you'll rely on
end-to-end at least once before you're in front of judges.

## Notes / non-goals

- No auth, single shared watchlist — matches the hackathon scope. `NOTIFY_EMAIL` is one global address, not per-user.
- No deployment — runs on `localhost` only.
- The 24-hour schedule is in-memory only; it doesn't need to survive a
  process restart (per spec) — on restart it just starts a fresh 24h countdown.
- Email is best-effort and non-blocking: if Resend isn't configured or a send
  fails, the check still completes and the dashboard still shows the change.
