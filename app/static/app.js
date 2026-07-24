async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

function fmtPrice(price, currency) {
  if (price === null || price === undefined) return "—";
  return `${currency || "USD"} ${price.toFixed(2)}`;
}

function fmtDate(iso) {
  if (!iso) return "never";
  return new Date(iso).toLocaleString();
}

// ---------- Dashboard ----------

let currentDraftItemId = null;

async function initDashboard() {
  await refreshItemsList();

  document.getElementById("add-item-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("item-name").value.trim();
    const thresholdRaw = document.getElementById("item-threshold").value;
    const threshold_price = thresholdRaw ? parseFloat(thresholdRaw) : null;
    if (!name) return;

    const item = await api("/api/items", {
      method: "POST",
      body: JSON.stringify({ name, threshold_price }),
    });
    currentDraftItemId = item.id;
    document.getElementById("search-item-name").textContent = item.name;
    document.getElementById("search-query").value = item.name;
    document.getElementById("search-panel").classList.remove("hidden");
    document.getElementById("add-item-form").reset();
    await refreshItemsList();
  });

  document.getElementById("search-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = document.getElementById("search-query").value.trim();
    if (!q) return;
    const resultsEl = document.getElementById("search-results");
    resultsEl.innerHTML = "Searching…";
    try {
      const candidates = await api(`/api/search?q=${encodeURIComponent(q)}`);
      renderCandidates(candidates);
    } catch (err) {
      resultsEl.innerHTML = `<p class="error-text">Search failed: ${err.message}</p>`;
    }
  });

  document.getElementById("done-adding").addEventListener("click", () => {
    document.getElementById("search-panel").classList.add("hidden");
    document.getElementById("search-results").innerHTML = "";
    currentDraftItemId = null;
    refreshItemsList();
  });
}

function renderCandidates(candidates) {
  const resultsEl = document.getElementById("search-results");
  if (!candidates.length) {
    resultsEl.innerHTML = "<p class='meta'>No results found.</p>";
    return;
  }
  resultsEl.innerHTML = "";
  for (const c of candidates) {
    const row = document.createElement("div");
    row.className = "candidate";
    row.innerHTML = `
      <div>
        <strong>[${c.store}]</strong> ${c.title}<br>
        <span class="meta">${fmtPrice(c.price, c.currency)} · <a href="${c.product_url}" target="_blank" rel="noopener">view</a></span>
      </div>
      <button data-url="${c.product_url}">Track this</button>
    `;
    row.querySelector("button").addEventListener("click", async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Adding…";
      try {
        await api(`/api/items/${currentDraftItemId}/listings`, {
          method: "POST",
          body: JSON.stringify({
            store: c.store,
            product_url: c.product_url,
            store_product_id: c.store_product_id,
            title: c.title,
          }),
        });
        e.target.textContent = "Tracking ✓";
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Failed — retry";
      }
    });
    resultsEl.appendChild(row);
  }
}

async function refreshItemsList() {
  const listEl = document.getElementById("items-list");
  const items = await api("/api/items");
  if (!items.length) {
    listEl.innerHTML = "<p class='meta'>No items yet — add one above.</p>";
    return;
  }
  listEl.innerHTML = "";
  for (const item of items) {
    const bestListing = item.listings
      .filter((l) => l.last_price !== null)
      .sort((a, b) => a.last_price - b.last_price)[0];
    const belowThreshold =
      item.threshold_price !== null &&
      bestListing &&
      bestListing.last_price <= item.threshold_price;

    const anyError = item.listings.some((l) => l.last_error);
    const allFailed = item.listings.length > 0 && !bestListing && anyError;

    let priceHtml;
    if (bestListing) {
      priceHtml = fmtPrice(bestListing.last_price, item.currency) + ` (${bestListing.store})`;
      if (bestListing.last_error) {
        priceHtml += ` <span class="error-text" title="${bestListing.last_error}">⚠ last check failed, price may be stale</span>`;
      }
    } else if (allFailed) {
      priceHtml = `<span class="error-text">⚠ scrape failing</span>`;
    } else {
      priceHtml = "no data yet";
    }

    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-row">
        <div>
          <a href="/items/${item.id}">${item.name}</a><br>
          <span class="meta">${item.listings.length} listing(s)${
      item.threshold_price !== null ? ` · alert below ${fmtPrice(item.threshold_price, item.currency)}` : ""
    }</span>
        </div>
        <div class="price ${belowThreshold ? "below-threshold" : ""}">
          ${priceHtml}
        </div>
      </div>
    `;
    listEl.appendChild(card);
  }
}

// ---------- Item detail ----------

let priceChart = null;

async function initItemDetail(itemId) {
  const item = await api(`/api/items/${itemId}`);
  renderItemHeader(item);
  renderListings(item);
  await renderChart(itemId);

  document.getElementById("edit-item-name").value = item.name;
  document.getElementById("edit-item-threshold").value =
    item.threshold_price !== null ? item.threshold_price : "";

  document.getElementById("edit-item-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("edit-item-name").value.trim();
    const thresholdRaw = document.getElementById("edit-item-threshold").value;
    const threshold_price = thresholdRaw ? parseFloat(thresholdRaw) : null;
    if (!name) return;

    const updated = await api(`/api/items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ name, threshold_price }),
    });
    renderItemHeader(updated);
  });

  document.getElementById("delete-item-button").addEventListener("click", async () => {
    if (!confirm(`Delete "${item.name}" and all its tracked listings and price history?`)) return;
    await api(`/api/items/${itemId}`, { method: "DELETE" });
    window.location.href = "/";
  });
}

function renderItemHeader(item) {
  const el = document.getElementById("item-header");
  el.innerHTML = `
    <h1>${item.name}</h1>
    <p class="meta">
      ${item.threshold_price !== null ? `Alert threshold: ${fmtPrice(item.threshold_price, item.currency)}` : "No alert threshold set"}
    </p>
  `;
}

function renderListings(item) {
  const el = document.getElementById("listings-list");
  if (!item.listings.length) {
    el.innerHTML = "<p class='meta'>No listings tracked for this item yet.</p>";
    return;
  }
  el.innerHTML = "";
  for (const l of item.listings) {
    const row = document.createElement("div");
    row.className = "card";
    row.innerHTML = `
      <div class="card-row">
        <div>
          <strong>[${l.store}]</strong> <a href="${l.product_url}" target="_blank" rel="noopener">${l.title || l.product_url}</a><br>
          <span class="meta">last checked: ${fmtDate(l.last_seen_at)}${l.last_in_stock === false ? " · out of stock" : ""}</span>
          ${l.last_error ? `<br><span class="error-text">${l.last_error}</span>` : ""}
        </div>
        <div>
          <span class="price">${fmtPrice(l.last_price, "")}</span>
          <button class="link" data-id="${l.id}">Remove</button>
        </div>
      </div>
    `;
    row.querySelector("button.link").addEventListener("click", async (e) => {
      if (!confirm("Stop tracking this listing?")) return;
      await api(`/api/listings/${l.id}`, { method: "DELETE" });
      row.remove();
    });
    el.appendChild(row);
  }
}

const CHART_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2"];

async function renderChart(itemId) {
  const points = await api(`/api/items/${itemId}/history`);
  const ctx = document.getElementById("price-chart");

  const byStore = {};
  for (const p of points) {
    (byStore[p.store] ||= []).push(p);
  }

  const datasets = Object.entries(byStore).map(([store, pts], i) => ({
    label: store,
    data: pts.map((p) => ({ x: new Date(p.scraped_at), y: p.price })),
    borderColor: CHART_COLORS[i % CHART_COLORS.length],
    tension: 0.2,
  }));

  if (priceChart) priceChart.destroy();
  priceChart = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      scales: {
        x: { type: "time", time: { unit: "day" } },
        y: { beginAtZero: false },
      },
    },
  });
}
