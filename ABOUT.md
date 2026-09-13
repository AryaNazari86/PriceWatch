# About PriceWatch

## Inspiration

The starting point wasn't a grand thesis about consumer behavior — it was a narrower, more stubborn question: could an "AI agent" project actually put the agent on the critical path, instead of bolting a chatbot onto a CRUD app and calling it agentic? A lot of price trackers exist. Almost none of them actually *look* at the page the way a person would — they hit an API, or they break the moment a store redesigns its checkout flow. Steel's whole premise (drop a real browser in the cloud, let something intelligent drive it) was a chance to build the version that doesn't care what the page looks like, because it never parsed the page's structure in the first place — it read it, the same way you would.

The name came before most of the code did. "Watch" already carries both meanings — a thing that keeps time, a thing that keeps looking — and once that was the frame, the countdown clock stopped being a UI decoration and became the actual mental model: this thing is *always about to check again*.

## How we built it

The stack is deliberately small: **Flask**, **Playwright** driving **Steel** cloud browser sessions, **Anthropic's Haiku 4.5** reading whatever text comes back, **Resend** for the one notification that matters, and a JSON file on disk instead of a database, because a hackathon watchlist does not need a schema migration story.

The interesting decision wasn't the framework — it was refusing to fake the parallelism. It would have been easy to loop over the watchlist and check products one at a time while calling it "an agent." Instead, `checker.py` opens one Steel session per product, all at once, each running in its own thread with its own `sync_playwright()` instance (Playwright's own docs say this is the one thing you're allowed to do with the sync API across threads — every other assumption about it is wrong). If checking one product takes time $T$, checking $N$ of them serially costs

$$ T_{\text{serial}} = \sum_{i=1}^{N} T_i \approx N \cdot T $$

while running them concurrently costs roughly

$$ T_{\text{parallel}} \approx \max(T_1, \dots, T_N) $$

That's not a theoretical claim in this codebase — it's a measured one. Four products, timestamps pulled straight from the request logs, showed all four Steel sessions created within 0.7 seconds of each other, and the whole batch finished in about the same time as the single slowest page. That number is the actual headline feature, not the countdown ring.

The extraction side stayed deliberately dumb on purpose: grab the page's visible text, hand it to the model with one instruction ("here's a product page, give me back this exact JSON shape"), and treat every possible malformed response — markdown fences around the JSON, prose wrapped around it, a flatly missing price — as an expected input to parse defensively, not an exception to catch later.

## Challenges we ran into

The one that took longest to *diagnose*, not fix: a real BestBuy listing would sometimes come back with a price and sometimes come back with nothing, and at first that looked like a model problem — like the LLM was just missing information that was clearly there. It wasn't. Fetching the raw page text twice, back to back, showed the price line was *genuinely absent* on one load and present on the next — an async pricing widget that hadn't finished rendering yet. The fix wasn't a better prompt, it was giving the page's network activity room to go quiet before reading it. The lesson generalized: in a scraping pipeline, the LLM is rarely the unreliable part. The page is.

The one that was a real bug, not a timing quirk: clicking "Refresh now" was quietly running the *entire* watchlist check twice — once from the manual trigger, once again from the background scheduler loop waking up and not knowing the work was already done. It hid well because both runs succeeded, so nothing looked broken; it just cost twice the Steel sessions and twice the LLM calls for one click. Caught by noticing two identical "checking N products" log lines with no user action in between, fixed by having the scheduler distinguish *why* it woke up before deciding whether to act on it.

The smallest one was almost the most instructive: a single `temperature=0` keyword argument, copied from what used to be a completely ordinary Anthropic API call, threw a runtime `TypeError` — not an API-level rejection, an SDK-level one. That parameter had quietly stopped existing in the currently-installed SDK version. Nothing else about the code was wrong. It was a small, concrete reminder that in this space, code that was correct three months ago isn't a safe assumption today — you check the installed version, not your memory of it.

And one that had nothing to do with code: Steel's browser runs somewhere else. It cannot see `localhost`. The self-hosted demo page — the one built specifically to make the "watch a price drop happen live" moment work — was unreachable by the exact agent meant to watch it, until a tunnel closed that gap. Which then surfaced a second, smaller trap: a free-tier tunnel shows first-time visitors an interstitial warning page, and a browser agent visiting for the first time is *always* a first-time visitor. Solved with one HTTP header, but only after nearly demoing a scrape of a warning screen instead of a product page.

## What we learned

Parallelism didn't need `asyncio` to be real. It needed a thread pool and a willingness to read Playwright's fine print instead of assuming the sync API would behave like the async one. And robustness in an agent that touches the live web isn't a property you design in once — it's a property you find by breaking against a real, messy, JavaScript-heavy page and then fixing exactly what actually failed, not what seemed likely to fail in theory.
