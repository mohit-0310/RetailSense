const state = {
  view: "agent",
  today: { priority: "high", page: 1, selected: null, data: null },
  store: { priority: "high", page: 1, selected: null, data: null, storeId: null },
};

const labels = {
  review_replenishment: "Review replenishment",
  markdown_review: "Review markdown",
  demand_drop_review: "Review demand drop",
  price_watch: "Price watch",
  monitor: "Monitor",
  no_urgent_action: "No urgent action",
  rising_unusually: "Rising faster than usual",
  falling_unusually: "Falling below usual movement",
  rising_watch: "Rising watch",
  falling_watch: "Falling watch",
  stable: "Stable",
  stable_low_activity: "Low activity",
};

function label(value) {
  return labels[value] || String(value || "").replaceAll("_", " ");
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  document.querySelector(`#${view}-view`).classList.add("active");
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === view);
  });
}

function renderOverview(data) {
  const summary = document.querySelector("#dashboard-summary");
  const findings = document.querySelector("#dashboard-findings");
  if (summary) {
    summary.innerHTML = `
      <div class="summary-tile emphasis"><span>High priority</span><strong>${data.priorities.high.toLocaleString()}</strong></div>
      <div class="summary-tile"><span>Review rows</span><strong>${data.total_item_store_rows.toLocaleString()}</strong></div>
      <div class="summary-tile"><span>Medium priority</span><strong>${data.priorities.medium.toLocaleString()}</strong></div>
      <div class="summary-tile"><span>Stores</span><strong>${data.stores.length}</strong></div>
    `;
  }
  if (findings) {
    findings.innerHTML = `
      <div class="finding"><span>01</span><strong>${data.priorities.high.toLocaleString()} high-priority item-store rows are ready for first review.</strong></div>
      <div class="finding"><span>02</span><strong>${data.priorities.medium.toLocaleString()} medium-priority rows show visible but less urgent movement.</strong></div>
      <div class="finding"><span>03</span><strong>${data.stores.length} stores have prepared review queues from M5 signals.</strong></div>
      <div class="finding"><span>04</span><strong>Demand, SNAP/event, and price context are available before action review.</strong></div>
    `;
  }
}

function queueRow(item, scope) {
  const active = state[scope].selected &&
    state[scope].selected.item_id === item.item_id &&
    state[scope].selected.store_id === item.store_id;
  return `
    <button class="queue-item ${active ? "active" : ""}" data-scope="${scope}" data-item="${item.item_id}" data-store="${item.store_id}">
      <div class="queue-top">
        <span class="item-title">${item.item_id} · ${item.store_id}</span>
        <span class="badge ${item.priority}">${item.priority}</span>
      </div>
      <p>${label(item.recommended_action)}. ${label(item.trend_label)}.</p>
    </button>
  `;
}

function renderQueue(scope) {
  const data = state[scope].data;
  const list = document.querySelector(`#${scope}-list`);
  const count = document.querySelector(`#${scope}-count`);
  const page = document.querySelector(`#${scope}-page`);
  const prev = document.querySelector(`#${scope}-prev`);
  const next = document.querySelector(`#${scope}-next`);

  if (!data) return;
  list.innerHTML = data.items.map((item) => queueRow(item, scope)).join("") || `<div class="empty"><p>No items in this queue.</p></div>`;
  count.textContent = `${data.total_items.toLocaleString()} ${data.priority} priority items`;
  page.textContent = `Page ${data.page} of ${data.total_pages}`;
  prev.disabled = !data.has_previous;
  next.disabled = !data.has_next;

  list.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", () => selectItem(scope, button.dataset.item, button.dataset.store));
  });
}

async function loadQueue(scope) {
  const current = state[scope];
  const params = new URLSearchParams({
    priority: current.priority,
    page: current.page,
    page_size: 15,
  });
  if (scope === "store" && current.storeId) params.set("store_id", current.storeId);
  const data = await getJson(`/api/recommendations?${params.toString()}`);
  current.data = data;
  renderQueue(scope);
}

async function selectItem(scope, itemId, storeId) {
  state[scope].selected = { item_id: itemId, store_id: storeId };
  renderQueue(scope);
  const detail = document.querySelector(`#${scope}-detail`);
  detail.classList.remove("empty");
  detail.innerHTML = `<p class="meta">Loading recommendation...</p>`;
  const item = await getJson(`/api/items/${encodeURIComponent(storeId)}/${encodeURIComponent(itemId)}`);
  renderDetail(scope, item);
}

function renderSparkline(daily) {
  const points = (daily || []).slice(-42);
  const max = Math.max(1, ...points.map((d) => Number(d.units || 0)));
  return `
    <div class="sparkline" aria-label="Recent daily movement">
      ${points.map((d) => `<span class="bar" title="${d.date}: ${d.units}" style="height:${Math.max(4, (Number(d.units || 0) / max) * 72)}px"></span>`).join("")}
    </div>
  `;
}

function renderDetail(scope, item) {
  const detail = document.querySelector(`#${scope}-detail`);
  const exp = item.explanation;
  const recentDaily = Number(item.recent_28_units || 0) / 28;
  const baselineDaily = Number(item.baseline_28_units || 0) / 28;
  const formatRate = (value) => value.toLocaleString(undefined, {
    maximumFractionDigits: value >= 10 ? 1 : 2,
  });
  detail.innerHTML = `
    <div class="detail-title">
      <h3>${item.item_id} · ${item.store_id}</h3>
      <span class="badge ${item.priority}">${item.priority}</span>
    </div>
    <div class="meta">${item.cat_id} / ${item.dept_id}</div>
    <div class="summary-grid">
      <div class="stat metric-card"><span>Recent avg</span><strong>${formatRate(recentDaily)}</strong><small>units/day</small></div>
      <div class="stat metric-card"><span>Baseline avg</span><strong>${formatRate(baselineDaily)}</strong><small>units/day</small></div>
      <div class="stat metric-card action-card"><span>Action</span><strong>${label(item.recommended_action)}</strong></div>
      <div class="stat"><span>Price</span><strong>${item.latest_sell_price ? `$${Number(item.latest_sell_price).toFixed(2)}` : "N/A"}</strong></div>
    </div>
    ${renderSparkline(item.daily_sales)}
    <div class="explain">
      <p>${exp.demand}</p>
      <p>${exp.event}</p>
      <p>${exp.price}</p>
      <p>${exp.recommendation}</p>
    </div>
  `;
}

function resetDetail(scope) {
  state[scope].selected = null;
  const detail = document.querySelector(`#${scope}-detail`);
  detail.classList.add("empty");
  detail.innerHTML = "<p>Select an item to review the recommendation.</p>";
}

async function initStores() {
  const stores = await getJson("/api/stores");
  const select = document.querySelector("#store-select");
  select.innerHTML = stores.map((store) => `<option value="${store.store_id}">${store.store_id}</option>`).join("");
  state.store.storeId = stores[0]?.store_id || null;
}

async function init() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  document.querySelectorAll("[data-jump]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.jump));
  });
  document.querySelectorAll(".priority").forEach((button) => {
    button.addEventListener("click", async () => {
      document.querySelectorAll(".priority").forEach((el) => el.classList.remove("active"));
      button.classList.add("active");
      state.today.priority = button.dataset.priority;
      state.today.page = 1;
      resetDetail("today");
      await loadQueue("today");
    });
  });
  document.querySelector("#today-prev").addEventListener("click", async () => {
    state.today.page -= 1;
    resetDetail("today");
    await loadQueue("today");
  });
  document.querySelector("#today-next").addEventListener("click", async () => {
    state.today.page += 1;
    resetDetail("today");
    await loadQueue("today");
  });
  document.querySelector("#store-prev").addEventListener("click", async () => {
    state.store.page -= 1;
    resetDetail("store");
    await loadQueue("store");
  });
  document.querySelector("#store-next").addEventListener("click", async () => {
    state.store.page += 1;
    resetDetail("store");
    await loadQueue("store");
  });
  document.querySelector("#store-select").addEventListener("change", async (event) => {
    state.store.storeId = event.target.value;
    state.store.page = 1;
    resetDetail("store");
    await loadQueue("store");
  });
  document.querySelector("#store-priority").addEventListener("change", async (event) => {
    state.store.priority = event.target.value;
    state.store.page = 1;
    resetDetail("store");
    await loadQueue("store");
  });
  document.querySelector("#clear-chat").addEventListener("click", () => {
    document.querySelector("#ask-input").value = "";
    document.querySelector("#chat-output").innerHTML = "";
  });
  document.querySelector("#ask-form").addEventListener("submit", submitAsk);

  const overview = await getJson("/api/overview");
  renderOverview(overview);
  await renderAgentStatus();
  await initStores();
  await loadQueue("today");
  await loadQueue("store");
}

async function renderAgentStatus() {
  try {
    const status = await getJson("/api/agent-status");
    const modeText = document.querySelector("#agent-mode-text");
    if (!modeText) return;
    modeText.textContent = status.mode === "openai-agents-sdk"
      ? `OpenAI Agents SDK enabled with ${status.model}.`
      : "Local fallback is active. Add OPENAI_API_KEY and set RETAILSENSE_USE_OPENAI_AGENTS=1 to use the OpenAI agent.";
  } catch (error) {
    // Keep the base placeholder text if status cannot be fetched.
  }
}

async function submitAsk(event) {
  event.preventDefault();
  const input = document.querySelector("#ask-input");
  const output = document.querySelector("#chat-output");
  const question = input.value.trim();
  if (!question) return;
  output.insertAdjacentHTML("beforeend", `<div class="message user">${question}</div>`);
  input.value = "";
  output.insertAdjacentHTML("beforeend", `<div class="message ai" id="pending-answer">Thinking...</div>`);
  try {
    const response = await getJson("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    document.querySelector("#pending-answer").textContent = response.answer;
    document.querySelector("#pending-answer").removeAttribute("id");
  } catch (error) {
    document.querySelector("#pending-answer").textContent = "Ask AI is unavailable right now. Please check that prepared data exists and the backend is running.";
    document.querySelector("#pending-answer").removeAttribute("id");
  }
  output.scrollTop = output.scrollHeight;
}

init().catch((error) => {
  document.querySelector(".main").innerHTML = `
    <section class="view active">
      <div class="section-head"><div><h2>RetailSense setup needed</h2><p>${error.message}</p></div></div>
    </section>
  `;
});
