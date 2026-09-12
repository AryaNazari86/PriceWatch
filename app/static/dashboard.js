(() => {
  const CIRCUMFERENCE = 2 * Math.PI * 82; // matches r=82 on .dial-progress

  const el = {
    dialProgress: document.getElementById("dial-progress"),
    dialTime: document.getElementById("dial-time"),
    dialStatus: document.getElementById("dial-status"),
    tickMarks: document.getElementById("tick-marks"),
    refreshBtn: document.getElementById("refresh-btn"),
    lastResult: document.getElementById("last-result"),
    statTotal: document.getElementById("stat-total"),
    statCount: document.getElementById("stat-count"),
    addForm: document.getElementById("add-form"),
    addError: document.getElementById("add-error"),
    inputUrl: document.getElementById("input-url"),
    watchlist: document.getElementById("watchlist"),
    emptyState: document.getElementById("empty-state"),
  };

  let state = JSON.parse(document.getElementById("initial-state").textContent);
  let serverOffsetMs = 0; // serverTime - Date.now(), so we don't trust the client's clock alone
  let nextCheckAtMs = 0;
  let fastPolling = false;
  let pollTimer = null;

  function drawTickMarks() {
    const cx = 100, cy = 100, r1 = 88, r2 = 80;
    let svg = "";
    for (let i = 0; i < 12; i++) {
      const angle = (i / 12) * 2 * Math.PI - Math.PI / 2;
      const x1 = cx + r1 * Math.cos(angle);
      const y1 = cy + r1 * Math.sin(angle);
      const x2 = cx + r2 * Math.cos(angle);
      const y2 = cy + r2 * Math.sin(angle);
      svg += `<line x1="${x1.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}" />`;
    }
    el.tickMarks.innerHTML = svg;
  }

  function formatHMS(totalSeconds) {
    totalSeconds = Math.max(0, Math.round(totalSeconds));
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
  }

  function formatMoney(value, currency) {
    if (value === null || value === undefined) return "—";
    const symbol = currency === "USD" || !currency ? "$" : currency + " ";
    return `${symbol}${Number(value).toFixed(2)}`;
  }

  function formatRelativeTime(iso) {
    if (!iso) return "never checked";
    const then = new Date(iso).getTime() + serverOffsetMs * 0;
    const diffSec = Math.round((Date.now() + serverOffsetMs - then) / 1000);
    if (diffSec < 5) return "just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str ?? "";
    return div.innerHTML;
  }

  function sparkline(history, strokeVar) {
    if (!history || history.length < 2) return "";
    const prices = history.map((p) => p.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;
    const w = 90, h = 26, pad = 2;
    const coords = prices.map((p, i) => {
      const x = pad + (i / (prices.length - 1)) * (w - pad * 2);
      const y = h - pad - ((p - min) / range) * (h - pad * 2);
      return [x, y];
    });
    const points = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    const fillId = `spark-fill-${Math.random().toString(36).slice(2, 9)}`;
    const areaPoints = `${pad},${h - pad} ${points} ${w - pad},${h - pad}`;
    const color = `var(${strokeVar || "--text-dim"})`;
    return `<svg class="pc-sparkline" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
      <defs>
        <linearGradient id="${fillId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.35" />
          <stop offset="100%" stop-color="${color}" stop-opacity="0" />
        </linearGradient>
      </defs>
      <polygon points="${areaPoints}" fill="url(#${fillId})" />
      <polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" />
    </svg>`;
  }

  const STATUS_LABEL = {
    watching: "Watching",
    dropped: "Price dropped!",
    increased: "Price increased",
    lowest: "Lowest ever",
    error: "Error",
    pending: "Checking soon",
  };

  const SPARK_COLOR = {
    dropped: "--gold",
    increased: "--danger",
    lowest: "--violet",
  };

  function productCard(p) {
    const statusClass = p.status || "pending";
    const stockNote = p.in_stock === false ? `<span class="out-of-stock">Out of stock</span>` : "";
    const errorNote = p.last_error ? `<span title="${escapeHtml(p.last_error)}">could not read price</span>` : "";
    const changeNote =
      p.last_change_amount != null
        ? `<span class="change-amount">${p.last_change_direction === "down" ? "-" : "+"}${formatMoney(p.last_change_amount, p.currency)}</span>`
        : "";
    return `
      <article class="product-card status-${statusClass}" data-id="${p.id}">
        <div class="pc-main">
          <p class="pc-title">
            <a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title || p.url)}</a>
            <svg viewBox="0 0 24 24" fill="none" width="12" height="12" aria-hidden="true"><path d="M7 17L17 7M17 7H9M17 7V15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </p>
          <div class="pc-meta">
            <span class="status-pill ${statusClass}">${STATUS_LABEL[statusClass] || statusClass}</span>
            <span>${p.last_checked ? "checked " + formatRelativeTime(p.last_checked) : "not checked yet"}</span>
            ${stockNote}
            ${errorNote}
          </div>
        </div>
        <div class="pc-prices">
          <div class="pc-current">${formatMoney(p.current_price, p.currency)}</div>
          ${changeNote ? `<div class="pc-target">${changeNote} since last check</div>` : ""}
          ${sparkline(p.price_history, SPARK_COLOR[statusClass])}
        </div>
        <button class="pc-remove" title="Remove from watchlist" aria-label="Remove from watchlist" data-remove="${p.id}">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 7H20M9 7V4.5C9 4.22386 9.22386 4 9.5 4H14.5C14.7761 4 15 4.22386 15 4.5V7M18 7L17.3 18.3C17.2 19.8 16 21 14.5 21H9.5C8 21 6.8 19.8 6.7 18.3L6 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </article>
    `;
  }

  function renderProducts() {
    const products = state.products || [];
    el.emptyState.hidden = products.length > 0;
    el.watchlist.querySelectorAll(".product-card").forEach((n) => n.remove());
    const html = products.map(productCard).join("");
    el.emptyState.insertAdjacentHTML("afterend", html);
  }

  function renderSummary() {
    const s = state.summary || { total_current_price: 0, item_count: 0 };
    el.statTotal.textContent = formatMoney(s.total_current_price, "USD");
    el.statCount.textContent = s.item_count;
  }

  function renderScheduler() {
    const sch = state.scheduler;
    if (!sch) return;
    serverOffsetMs = new Date(sch.server_time).getTime() - Date.now();
    nextCheckAtMs = new Date(sch.next_check_at).getTime();
    el.dialProgress.classList.toggle("checking", sch.is_checking);
    el.dialStatus.textContent = sch.is_checking ? "checking now…" : "next check";
    el.refreshBtn.disabled = sch.is_checking;
    el.refreshBtn.querySelector(".crown-icon").classList.toggle("spin", sch.is_checking);
    el.lastResult.textContent = sch.last_result_summary || "";

    if (sch.is_checking && !fastPolling) startFastPolling();
    if (!sch.is_checking && fastPolling) stopFastPolling();
  }

  function renderAll() {
    renderSummary();
    renderProducts();
    renderScheduler();
  }

  function tickClock() {
    const remainingSec = (nextCheckAtMs - (Date.now() + serverOffsetMs)) / 1000;
    el.dialTime.textContent = formatHMS(remainingSec);
    const interval = (state.scheduler && state.scheduler.interval_seconds) || 86400;
    const fraction = Math.max(0, Math.min(1, remainingSec / interval));
    el.dialProgress.style.strokeDashoffset = String(CIRCUMFERENCE * (1 - fraction));
  }

  async function fetchState() {
    try {
      const res = await fetch("/api/state");
      state = await res.json();
      renderAll();
    } catch (e) {
      // Network hiccup — the next poll will retry. Keep the last known state on screen.
      console.warn("Failed to refresh state", e);
    }
  }

  function startFastPolling() {
    fastPolling = true;
    clearInterval(pollTimer);
    pollTimer = setInterval(fetchState, 1200);
  }

  function stopFastPolling() {
    fastPolling = false;
    clearInterval(pollTimer);
    pollTimer = setInterval(fetchState, 6000);
  }

  el.addForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    el.addError.hidden = true;
    const url = el.inputUrl.value.trim();
    try {
      const res = await fetch("/api/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not add product");
      state = data;
      renderAll();
      el.addForm.reset();
      startFastPolling(); // catch the just-added product's first check quickly
      setTimeout(() => { if (!state.scheduler.is_checking) stopFastPolling(); }, 8000);
    } catch (err) {
      el.addError.textContent = err.message;
      el.addError.hidden = false;
    }
  });

  el.watchlist.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-remove]");
    if (!btn) return;
    const id = btn.dataset.remove;
    btn.disabled = true;
    try {
      const res = await fetch(`/api/products/${id}`, { method: "DELETE" });
      state = await res.json();
      renderAll();
    } catch (err) {
      btn.disabled = false;
    }
  });

  el.refreshBtn.addEventListener("click", async () => {
    el.refreshBtn.disabled = true;
    el.refreshBtn.querySelector(".crown-icon").classList.add("spin");
    try {
      const res = await fetch("/api/refresh", { method: "POST" });
      state = await res.json();
      renderAll();
      startFastPolling();
    } catch (err) {
      el.refreshBtn.disabled = false;
    }
  });

  drawTickMarks();
  renderAll();
  setInterval(tickClock, 1000);
  tickClock();
  pollTimer = setInterval(fetchState, 6000);
})();
