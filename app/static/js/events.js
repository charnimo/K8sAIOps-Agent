import { ApiClient } from "./api.js";
import { AuthManager } from "./auth.js";

let ws = null;
let events = [];
let selectedId = null;
let filterLevel = "ALL";
let searchQuery = "";
let nsTags = new Set();
let teamTags = new Set();
let nsSeen = {};
let stats = { CRITICAL: 0, WARNING: 0, INFO: 0 };

const auth = new AuthManager();
const token = auth.getToken();
if (!token) window.location.href = "/static/login.html";

const api = new ApiClient(token);

function attachToGlobalWs() {
    const ws = window._globalWs;
    if (!ws) return;

    ws.addEventListener('message', (raw) => {
        try {
            const msg = JSON.parse(raw.data);
            if (msg.type === 'SUBSCRIBED' && msg.history)
                msg.history.forEach(ingestEvent);
            else if (msg.type === 'HISTORY')
                msg.events.forEach(ingestEvent);
            else if (msg.type !== 'PONG' && msg.type !== 'SUBSCRIBED')
                ingestEvent(msg);
        } catch (_) {}
    });

    setWsStatus(ws.readyState === 1 ? 'connected' : 'connecting');
}

function setWsStatus(state) {
  const dot = document.getElementById("wsDot");
  const lbl = document.getElementById("wsStatus");
  if (dot) dot.className = "ws-dot " + state;
  if (lbl)
    lbl.textContent =
      {
        connected: "Connected",
        connecting: "Connecting…",
        error: "Error",
        "": "Disconnected",
      }[state] || "Disconnected";
}

function getSelectedSeverities() {
  return ["CRITICAL", "WARNING", "INFO"].filter(
    (s) => document.getElementById(`sev-${s}`)?.checked,
  );
}

function updateSubscription() {
    const ws = window._globalWs;
    if (!ws || ws.readyState !== 1) return;
    ws.send(JSON.stringify({
        type:       'UPDATE_SUBSCRIPTION',
        namespaces: [...nsTags],
        severities: getSelectedSeverities(),
    }));
}

function ingestEvent(evt) {
  events.unshift(evt);
  if (events.length > 500) events.pop();
  stats[evt.severity]++;
  document.getElementById("statCrit").innerText = stats.CRITICAL;
  document.getElementById("statWarn").innerText = stats.WARNING;
  document.getElementById("statInfo").innerText = stats.INFO;

  nsSeen[evt.namespace] = (nsSeen[evt.namespace] || 0) + 1;
  renderNsList();
  renderFeed();

  // Toast notifications for critical/warning
  if (evt.severity === "CRITICAL") {
    window.showToast(`🔴 ${evt.reason} · ${evt.resource_name}`, "error");
    document.title = "🔴 " + evt.reason;
    setTimeout(() => (document.title = "Live Events · AIOps"), 5000);
  } else if (evt.severity === "WARNING") {
    window.showToast(`⚠️ ${evt.reason} · ${evt.resource_name}`, "warning");
  }
}

function renderFeed() {
  const feed = document.getElementById("feed");
  if (!feed) return;
  const filtered = events.filter((e) => {
    if (filterLevel !== "ALL" && e.severity !== filterLevel) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        e.resource_name?.toLowerCase().includes(q) ||
        e.namespace?.toLowerCase().includes(q) ||
        e.message?.toLowerCase().includes(q) ||
        e.reason?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  if (!filtered.length) {
    feed.innerHTML = `<div class="detail-empty"><div style="font-size:24px">⬡</div><div>No events match</div></div>`;
    return;
  }

  feed.innerHTML = filtered
    .map(
      (e) => `
    <div class="event-card ${e.severity} ${e.event_id === selectedId ? "selected" : ""}" data-event-id="${e.event_id}">
      <div class="event-header">
        <span class="severity-badge sev-${e.severity}">${e.severity}</span>
        <span class="event-type">${e.event_type}</span>
        <span class="event-time">${timeAgo(e.timestamp)}</span>
      </div>
      <div class="event-resource"><span class="ns">${e.namespace}/</span>${e.resource_name}</div>
      <div class="event-message">${truncate(e.message, 90)}</div>
    </div>
  `,
    )
    .join("");

  document.querySelectorAll(".event-card").forEach((card) => {
    card.addEventListener("click", () => {
      const id = card.getAttribute("data-event-id");
      selectedId = id;
      const evt = events.find((e) => e.event_id === id);
      if (evt) renderDetail(evt);
      renderFeed(); // re-render to highlight selected
    });
  });
}

function renderDetail(e) {
  const colorMap = { CRITICAL: "red", WARNING: "yellow", INFO: "green" };
  const c = colorMap[e.severity];
  const labelChips = Object.entries({ ...e.labels, ...e.annotations })
    .filter(([k]) => !k.startsWith("kubectl"))
    .map(([k, v]) => `<span class="label-chip">${k}=${v}</span>`)
    .join("");

  document.getElementById("detailPane").innerHTML = `
    <div class="detail-section">
      <div class="detail-kv">
        <span class="kv-key">Event ID</span>   <span class="kv-val" style="font-size:10px">${e.event_id}</span>
        <span class="kv-key">Severity</span>   <span class="kv-val ${c}">${e.severity}</span>
        <span class="kv-key">Type</span>        <span class="kv-val" style="color:var(--purple)">${e.event_type}</span>
        <span class="kv-key">Reason</span>      <span class="kv-val ${c}">${e.reason}</span>
        <span class="kv-key">Namespace</span>   <span class="kv-val" style="color:var(--accent)">${e.namespace}</span>
        <span class="kv-key">Resource</span>    <span class="kv-val">${e.resource_name}</span>
        <span class="kv-key">Kind</span>         <span class="kv-val">${e.resource_kind}</span>
        <span class="kv-key">Node</span>         <span class="kv-val">${e.node || "—"}</span>
        <span class="kv-key">Count</span>        <span class="kv-val">${e.raw_count || 1}</span>
        <span class="kv-key">Timestamp</span>   <span class="kv-val" style="font-size:10px">${new Date(e.timestamp).toLocaleString()}</span>
      </div>
    </div>
    <div class="detail-section">
      <div class="sub-label" style="margin-bottom:6px">Message</div>
      <div style="font-size:11px; line-height:1.6">${e.message}</div>
    </div>
  `;
}

function renderNsList() {
  const sorted = Object.entries(nsSeen).sort((a, b) => b[1] - a[1]);
  document.getElementById("nsList").innerHTML = sorted
    .map(
      ([ns, cnt]) => `
    <div class="ns-item" data-ns="${ns}">
      <div class="ns-dot"></div><span>${ns}</span><span class="ns-count">${cnt}</span>
    </div>
  `,
    )
    .join("");
  document.querySelectorAll(".ns-item").forEach((el) => {
    el.addEventListener("click", () => {
      searchQuery = el.getAttribute("data-ns");
      document.getElementById("searchInput").value = searchQuery;
      renderFeed();
    });
  });
}

function timeAgo(ts) {
  const sec = Math.floor((Date.now() - new Date(ts)) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
}
function truncate(str, n) {
  return str.length > n ? str.slice(0, n) + "…" : str;
}

// Tag handling
function addTag(evt, type) {
  if (evt.key !== "Enter") return;
  const field = evt.target;
  const val = field.value.trim();
  if (!val) return;
  field.value = "";
  const set = type === "ns" ? nsTags : teamTags;
  set.add(val);
  renderTags(type);
  updateSubscription();
}

function renderTags(type) {
  const containerId = type === "ns" ? "nsTagInput" : "teamTagInput";
  const set = type === "ns" ? nsTags : teamTags;
  const container = document.getElementById(containerId);
  if (!container) return;
  const inputField = container.querySelector(".tag-input-field");
  [...container.querySelectorAll(".tag")].forEach((t) => t.remove());
  set.forEach((val) => {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.innerHTML = `${val}<span class="rm" data-val="${val}" data-type="${type}">×</span>`;
    container.insertBefore(tag, inputField);
  });
  document.querySelectorAll(".tag .rm").forEach((rm) => {
    rm.addEventListener("click", (e) => {
      const val = rm.getAttribute("data-val");
      const t = rm.getAttribute("data-type");
      const set2 = t === "ns" ? nsTags : teamTags;
      set2.delete(val);
      renderTags(t);
      updateSubscription();
    });
  });
}

// Initialization
document.addEventListener("DOMContentLoaded", () => {
  attachToGlobalWs();

  // Filter buttons
  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      filterLevel = btn.getAttribute("data-filter");
      document
        .querySelectorAll(".filter-btn")
        .forEach((b) =>
          b.classList.remove(
            "active-all",
            "active-crit",
            "active-warn",
            "active-info",
          ),
        );
      btn.classList.add(`active-${filterLevel.toLowerCase()}`);
      renderFeed();
    });
  });

  document.getElementById("clearFeedBtn")?.addEventListener("click", () => {
    events = [];
    stats = { CRITICAL: 0, WARNING: 0, INFO: 0 };
    document.getElementById("statCrit").innerText = "0";
    document.getElementById("statWarn").innerText = "0";
    document.getElementById("statInfo").innerText = "0";
    nsSeen = {};
    selectedId = null;
    renderNsList();
    renderFeed();
    document.getElementById("detailPane").innerHTML =
      `<div class="detail-empty"><div style="font-size:24px">◈</div><div>Select an event</div></div>`;
  });

  document.getElementById("searchInput")?.addEventListener("input", (e) => {
    searchQuery = e.target.value;
    renderFeed();
  });

  document
    .getElementById("applyFiltersBtn")
    ?.addEventListener("click", updateSubscription);
  document
    .getElementById("nsField")
    ?.addEventListener("keydown", (e) => addTag(e, "ns"));
  document
    .getElementById("teamField")
    ?.addEventListener("keydown", (e) => addTag(e, "team"));

  ["sev-CRITICAL", "sev-WARNING", "sev-INFO"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", updateSubscription);
  });
});
