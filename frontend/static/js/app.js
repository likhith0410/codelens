"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  sessionId:   null,
  currentQaId: null,
  currentTags: [],
};

// ── DOM helpers ───────────────────────────────────────────────────────────────
function el(id)   { return document.getElementById(id); }
function show(id) { const e = el(id); if (e) e.classList.remove("hidden"); }
function hide(id) { const e = el(id); if (e) e.classList.add("hidden"); }

function showToast(msg, isError = true) {
  const t = document.createElement("div");
  t.textContent = (isError ? "⚠ " : "✓ ") + msg;
  Object.assign(t.style, {
    position: "fixed", bottom: "1.5rem", left: "50%",
    transform: "translateX(-50%)",
    background: isError ? "rgba(255,78,106,.15)" : "rgba(0,229,160,.15)",
    border: `1px solid ${isError ? "rgba(255,78,106,.5)" : "rgba(0,229,160,.5)"}`,
    color: isError ? "#ff4e6a" : "#00e5a0",
    fontFamily: "var(--fm)", fontSize: ".82rem",
    padding: ".7rem 1.3rem", borderRadius: "8px",
    zIndex: 9999, maxWidth: "90vw", textAlign: "center",
    boxShadow: "0 4px 20px rgba(0,0,0,.4)",
  });
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4500);
}

async function apiFetch(url, opts = {}) {
  const res  = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initDropzone();
  initAsk();
  restoreSession();
});

// ── Tabs ──────────────────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      const tab = el("tab-" + btn.dataset.tab);
      if (tab) tab.classList.add("active");
    });
  });
}

// ── Dropzone ──────────────────────────────────────────────────────────────────
function initDropzone() {
  const zone  = el("dropzone");
  const input = el("file-input");
  if (!zone || !input) return;

  // Click on zone (but NOT on the browse span — that calls input.click() directly)
  zone.addEventListener("click", (e) => {
    // If click came from the .file-label span, let that span handle it
    if (e.target.classList.contains("file-label")) return;
    input.click();
  });

  zone.addEventListener("dragover", e => {
    e.preventDefault();
    zone.classList.add("drag-over");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) uploadZip(file);
  });

  input.addEventListener("change", () => {
    if (input.files && input.files[0]) uploadZip(input.files[0]);
    // Reset so same file can be re-selected
    input.value = "";
  });
}

// ── Upload ZIP ────────────────────────────────────────────────────────────────
async function uploadZip(file) {
  if (!file.name.toLowerCase().endsWith(".zip")) {
    showToast("Please upload a .zip file.");
    return;
  }

  setProgress(5);
  el("status-text").textContent = "Uploading and indexing codebase…";
  show("ingest-status");
  hide("ingest-success");

  animateProgress(5, 75, 4000);

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");

    setProgress(100);
    await delay(400);
    onIngestSuccess(data);
  } catch (e) {
    hide("ingest-status");
    showToast(e.message);
  }
}

// ── GitHub ────────────────────────────────────────────────────────────────────
async function loadGithub() {
  const url = (el("github-url")?.value || "").trim();
  if (!url) { showToast("Please enter a GitHub URL."); return; }

  setProgress(5);
  el("status-text").textContent = "Fetching repo from GitHub…";
  show("ingest-status");
  hide("ingest-success");

  animateProgress(5, 65, 6000);

  try {
    const data = await apiFetch("/api/github", {
      method: "POST",
      body: JSON.stringify({ repo_url: url }),
    });
    setProgress(100);
    await delay(400);
    onIngestSuccess(data);
  } catch (e) {
    hide("ingest-status");
    showToast(e.message);
  }
}

// ── Ingest success ────────────────────────────────────────────────────────────
function onIngestSuccess(data) {
  state.sessionId = data.session_id;
  localStorage.setItem("codelens_session", state.sessionId);

  const s = data.stats || {};
  el("success-source").textContent = data.source || "codebase";
  el("success-stats").textContent  =
    `${s.files_indexed || 0} files · ${s.total_chunks || 0} chunks · ${s.files_skipped || 0} skipped`;

  hide("ingest-status");
  show("ingest-success");

  const badge = el("nav-session-badge");
  if (badge) {
    badge.textContent = "Session: " + data.session_id.slice(0, 8);
    badge.classList.remove("hidden");
  }

  show("panel-ask");
  show("panel-history");
  loadHistory();

  setTimeout(() => {
    el("panel-ask")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 250);
}

// ── Reset ─────────────────────────────────────────────────────────────────────
function resetSession() {
  state.sessionId   = null;
  state.currentQaId = null;
  state.currentTags = [];
  localStorage.removeItem("codelens_session");

  hide("ingest-success");
  hide("ingest-status");
  hide("panel-ask");
  hide("panel-answer");
  hide("panel-history");
  hide("nav-session-badge");

  const fi = el("file-input");
  if (fi) fi.value = "";
  const gu = el("github-url");
  if (gu) gu.value = "";
}

// ── Ask ───────────────────────────────────────────────────────────────────────
function initAsk() {
  const btn = el("btn-ask");
  if (btn) btn.addEventListener("click", askQuestion);

  const qa = el("question-input");
  if (qa) qa.addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) askQuestion();
  });
}

function fillQuestion(btn) {
  const qi = el("question-input");
  if (qi) { qi.value = btn.textContent.trim(); qi.focus(); }
}

async function askQuestion() {
  const question = (el("question-input")?.value || "").trim();
  if (!question)         { showToast("Please type a question.");           return; }
  if (!state.sessionId)  { showToast("Please upload a codebase first.");   return; }

  const btn     = el("btn-ask");
  const refactor = el("refactor-toggle")?.checked || false;

  if (btn) btn.disabled = true;
  hide("ask-btn-text");
  show("ask-spinner");

  try {
    const data = await apiFetch("/api/ask", {
      method: "POST",
      body: JSON.stringify({
        session_id:        state.sessionId,
        question,
        generate_refactor: refactor,
      }),
    });
    renderAnswer(question, data);
    loadHistory();
  } catch (e) {
    showToast(e.message);
  } finally {
    if (btn) btn.disabled = false;
    show("ask-btn-text");
    hide("ask-spinner");
  }
}

// ── Render answer ─────────────────────────────────────────────────────────────
function renderAnswer(question, data) {
  state.currentQaId = data.qa_id || null;
  state.currentTags = [];

  const ql = el("answer-question-label");
  if (ql) ql.textContent = `"${question}"`;

  const ac = el("answer-content");
  if (ac) {
    ac.innerHTML = marked.parse(data.answer || "No answer returned.");
    ac.querySelectorAll("pre code").forEach(b => hljs.highlightElement(b));
  }

  // Snippets
  const snippets = data.snippets || [];
  if (snippets.length) {
    const sc = el("snippets-count");
    if (sc) sc.textContent = `${snippets.length} chunk${snippets.length !== 1 ? "s" : ""}`;
    const sl = el("snippets-list");
    if (sl) {
      sl.innerHTML = "";
      snippets.forEach((s, i) => renderSnippet(s, i, sl));
    }
    show("snippets-section");
  } else {
    hide("snippets-section");
  }

  // Refactor
  if (data.refactor_suggestions) {
    const rc = el("refactor-content");
    if (rc) {
      rc.innerHTML = marked.parse(data.refactor_suggestions);
      rc.querySelectorAll("pre code").forEach(b => hljs.highlightElement(b));
    }
    show("refactor-section");
  } else {
    hide("refactor-section");
  }

  // Tags
  renderTags([]);
  show("tags-row");
  show("panel-answer");

  setTimeout(() => {
    el("panel-answer")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 100);
}

function renderSnippet(s, idx, container) {
  const score = Math.round((s.score || 0) * 100);
  const lang  = s.language || "text";

  const card = document.createElement("div");
  card.className = "snippet-card" + (idx < 2 ? " open" : "");
  card.innerHTML = `
    <div class="snippet-header">
      <span class="snippet-score">${score}%</span>
      <span class="snippet-file">${esc(s.file)}</span>
      <span class="snippet-lines">lines ${s.line_start}–${s.line_end}</span>
      <span class="snippet-toggle">▾</span>
    </div>
    <div class="snippet-body">
      <pre><code class="language-${lang}">${esc(s.raw || "")}</code></pre>
    </div>
  `;
  card.querySelector(".snippet-header").addEventListener("click", () => {
    card.classList.toggle("open");
  });
  card.querySelectorAll("pre code").forEach(b => hljs.highlightElement(b));
  container.appendChild(card);
}

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── Tags ──────────────────────────────────────────────────────────────────────
function renderTags(tags) {
  state.currentTags = [...tags];
  const c = el("tags-container");
  if (!c) return;
  c.innerHTML = "";
  tags.forEach(tag => {
    const pill = document.createElement("span");
    pill.className = "tag-pill";
    pill.innerHTML = `${esc(tag)} <button onclick="removeTag('${esc(tag)}')" title="Remove">×</button>`;
    c.appendChild(pill);
  });
}

function addTag() {
  const input = el("tag-input");
  if (!input) return;
  const val = input.value.trim().toLowerCase().replace(/\s+/g, "-");
  if (!val || state.currentTags.includes(val)) { input.value = ""; return; }
  state.currentTags.push(val);
  renderTags(state.currentTags);
  input.value = "";
  saveTags();
}

function removeTag(tag) {
  state.currentTags = state.currentTags.filter(t => t !== tag);
  renderTags(state.currentTags);
  saveTags();
}

async function saveTags() {
  if (!state.currentQaId) return;
  try {
    await apiFetch("/api/tag", {
      method: "POST",
      body: JSON.stringify({ qa_id: state.currentQaId, tags: state.currentTags }),
    });
    loadHistory();
  } catch (e) {
    showToast("Could not save tags: " + e.message);
  }
}

// ── History ───────────────────────────────────────────────────────────────────
async function loadHistory(query = "") {
  if (!state.sessionId) return;
  try {
    let records;
    if (query) {
      const d = await apiFetch("/api/search-history", {
        method: "POST",
        body: JSON.stringify({ session_id: state.sessionId, query }),
      });
      records = d.results;
    } else {
      const d = await apiFetch(`/api/history/${state.sessionId}`);
      records = d.history;
    }
    renderHistory(records);
  } catch (_) {}
}

function renderHistory(records) {
  const list = el("history-list");
  if (!list) return;
  if (!records || !records.length) {
    list.innerHTML = `<div class="history-empty">No Q&As yet. Ask your first question above!</div>`;
    return;
  }
  list.innerHTML = "";
  records.forEach(rec => {
    const item = document.createElement("div");
    item.className = "history-item";
    const tags  = (rec.tags || []).map(t => `<span class="history-tag">${esc(t)}</span>`).join("");
    const date  = (rec.created_at || "").slice(0, 16).replace("T", " ");
    const count = (rec.snippets || []).length;
    item.innerHTML = `
      <div class="history-item-q">${esc(rec.question)}</div>
      <div class="history-item-meta">
        <span>${date} UTC</span>
        <span>${count} snippet${count !== 1 ? "s" : ""}</span>
      </div>
      ${tags ? `<div class="history-item-tags">${tags}</div>` : ""}
    `;
    item.addEventListener("click", () => {
      el("question-input").value = rec.question;
      renderAnswer(rec.question, rec);
    });
    list.appendChild(item);
  });
}

let _histTimer;
function onHistorySearch(val) {
  clearTimeout(_histTimer);
  _histTimer = setTimeout(() => loadHistory(val.trim()), 350);
}

// ── Export ────────────────────────────────────────────────────────────────────
function exportSession() {
  if (!state.sessionId) { showToast("No active session."); return; }
  window.open(`/api/export/${state.sessionId}`, "_blank");
}

// ── Restore session from localStorage ────────────────────────────────────────
async function restoreSession() {
  const saved = localStorage.getItem("codelens_session");
  if (!saved) return;
  try {
    const session = await apiFetch(`/api/sessions/${saved}`);
    state.sessionId = saved;

    el("success-source").textContent = session.source || "Previous session";
    const s = session.stats || {};
    el("success-stats").textContent =
      `${s.files_indexed || 0} files · ${s.total_chunks || 0} chunks`;

    show("ingest-success");
    show("panel-ask");
    show("panel-history");

    const badge = el("nav-session-badge");
    if (badge) {
      badge.textContent = "Session: " + saved.slice(0, 8);
      badge.classList.remove("hidden");
    }
    loadHistory();
  } catch (_) {
    localStorage.removeItem("codelens_session");
  }
}

// ── Progress bar helpers ──────────────────────────────────────────────────────
function setProgress(pct) {
  const bar = el("progress-bar");
  if (bar) bar.style.width = pct + "%";
}

let _progTimer;
function animateProgress(from, to, durationMs) {
  clearInterval(_progTimer);
  const steps     = 40;
  const interval  = durationMs / steps;
  const increment = (to - from) / steps;
  let current     = from;
  setProgress(current);
  _progTimer = setInterval(() => {
    current += increment;
    if (current >= to) { setProgress(to); clearInterval(_progTimer); }
    else setProgress(current);
  }, interval);
}