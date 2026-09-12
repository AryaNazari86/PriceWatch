"""24-hour background auto-check loop, plus manual "refresh now".

Runs as a single daemon thread. Owns `next_check_at` (a UTC timestamp) so the
frontend can render a live countdown that survives page reloads — reloading
the dashboard just re-fetches this same timestamp, it never resets the clock.

Persistence of the schedule across process restarts is intentionally not
required (per spec) — this is in-memory only, for the life of the running app.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from . import config
from .checker import check_all_products

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, interval_seconds: int, check_fn=check_all_products):
        self.interval_seconds = interval_seconds
        self._check_fn = check_fn

        self._lock = threading.Lock()
        self._wake_event = threading.Event()
        self._next_check_at = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
        self._is_checking = False
        self._last_result_summary: str | None = None

        self._thread = threading.Thread(target=self._run_loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run_loop(self) -> None:
        while True:
            with self._lock:
                remaining = (self._next_check_at - datetime.now(timezone.utc)).total_seconds()
            woke_via_event = self._wake_event.wait(timeout=max(0.0, remaining))
            self._wake_event.clear()
            if woke_via_event:
                # A manual trigger already ran the check (see _trigger_and_run)
                # and updated next_check_at — just loop back and recompute the
                # wait against it. Running _run_check() here too would check
                # the whole watchlist twice for one "refresh now" click.
                continue
            # Timeout elapsed naturally: this is the scheduled 24h check.
            self._run_check()

    def _run_check(self) -> None:
        with self._lock:
            self._is_checking = True
        try:
            results = self._check_fn()
            with self._lock:
                self._last_result_summary = f"Checked {len(results)} product(s)."
        except Exception as exc:  # noqa: BLE001 — the loop must never die
            logger.exception("Watchlist check failed")
            with self._lock:
                self._last_result_summary = f"Check failed: {exc}"
        finally:
            with self._lock:
                self._is_checking = False
                self._next_check_at = datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)

    def trigger_now(self) -> None:
        """Wake the loop immediately (used by the "refresh now" button).

        Runs the check synchronously in a background thread so the HTTP
        request that triggered it can return right away; the dashboard polls
        /api/state to see progress and results.
        """
        threading.Thread(target=self._trigger_and_run, daemon=True).start()

    def _trigger_and_run(self) -> None:
        # Skip if a check is already in flight.
        with self._lock:
            if self._is_checking:
                return
        self._run_check()
        # Wake the main loop so it recomputes its wait against the new next_check_at.
        self._wake_event.set()

    def state(self) -> dict:
        with self._lock:
            now = datetime.now(timezone.utc)
            seconds_remaining = max(0, int((self._next_check_at - now).total_seconds()))
            return {
                "next_check_at": self._next_check_at.isoformat(),
                "seconds_remaining": seconds_remaining,
                "interval_seconds": self.interval_seconds,
                "is_checking": self._is_checking,
                "last_result_summary": self._last_result_summary,
                "server_time": now.isoformat(),
            }


scheduler = Scheduler(interval_seconds=config.CHECK_INTERVAL_SECONDS)
