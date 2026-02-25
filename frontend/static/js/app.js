"use strict";

/*
 * app.js — CodeLens frontend
 *
 * Security: All user-controlled or LLM-generated content is sanitised
 * with DOMPurify before being inserted via innerHTML. Direct string
 * interpolation into innerHTML is never used for untrusted data —
 * untrusted values go through the esc() helper or DOM APIs only.
 */

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

/** Escape a value for safe inclusion in HTML text nodes. */
function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
}

/**
 * Safely render Markdown. DOMPurify strips any scripts or event
 * handlers that a malicious LLM response or injected snippet might contain.
 */
function safeMarkdown(md) {
  const raw = marked.parse(md || "");
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS: [
      "p","br","strong","em","code","pre","h1","h2","h3","h4",
      "ul","ol","li","blockquote","a","hr","table","thead","tbody",
      "tr","th","td","span","div",
    ],
    ALLOWED_ATTR: ["href","class","target","rel"],
    FORCE_BODY: true,
  });
}

/** Set text content safely — never innerHTML. */
function setText(id, value) {
  const e = el(id);
  if (e) e.textContent = String(value ?? "");
}

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

  zone.addEventListener("click", (e) => {
    if (e.target.classList.contains("file-label")) return;
    input.click();
  });
  zone.addEventListener("dragover",  e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", ()  => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) uploadZip(file);
  });
  input.addEventListener("change", () => {
    if (input.files?.[0]) uploadZip(input.files[0]);
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
  setText("status-text", "Uploading and indexing codebase…");
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
  setText("status-text", "Fetching repo from GitHub…");
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
  // Use textContent — never innerHTML — for user/API-supplied strings
  setText("success-source", data.source || "codebase");
  setText("success-stats",
    `${s.files_indexed ?? 0} files · ${s.total_chunks ?? 0} chunks · ${s.files_skipped ?? 0} skipped`);

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
  setTimeout(() => el("panel-ask")?.scrollIntoView({ behavior: "smooth", block: "start" }), 250);
}

// ── Reset ─────────────────────────────────────────────────────────────────────
function resetSession() {
  state.sessionId = state.currentQaId = null;
  state.currentTags = [];
  localStorage.removeItem("codelens_session");
  ["ingest-success","ingest-status","panel-ask","panel-answer","panel-history","nav-session-badge"]
    .forEach(hide);
  const fi = el("file-input"); if (fi) fi.value = "";
  const gu = el("github-url"); if (gu) gu.value = "";
}

// ── Ask ───────────────────────────────────────────────────────────────────────
function initAsk() {
  el("btn-ask")?.addEventListener("click", askQuestion);
  el("question-input")?.addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) askQuestion();
  });
}

function fillQuestion(btn) {
  const qi = el("question-input");
  if (qi) { qi.value = btn.textContent.trim(); qi.focus(); }
}

async function askQuestion() {
  const question = (el("question-input")?.value || "").trim();
  if (!question)        { showToast("Please type a question.");          return; }
  if (!state.sessionId) { showToast("Please upload a codebase first.");  return; }

  const btn      = el("btn-ask");
  const refactor = el("refactor-toggle")?.checked || false;
  if (btn) btn.disabled = true;
  hide("ask-btn-text");
  show("ask-spinner");

  try {
    const data = await apiFetch("/api/ask", {
      method: "POST",
      body: JSON.stringify({ session_id: state.sessionId, question, generate_refactor: refactor }),
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

  // Safe: textContent only
  setText("answer-question-label", `"${question}"`);

  // Safe: DOMPurify-sanitised markdown
  const ac = el("answer-content");
  if (ac) {
    ac.innerHTML = safeMarkdown(data.answer);
    ac.querySelectorAll("pre code").forEach(b => hljs.highlightElement(b));
  }

  const snippets = data.snippets || [];
  if (snippets.length) {
    setText("snippets-count", `${snippets.length} chunk${snippets.length !== 1 ? "s" : ""}`);
    const sl = el("snippets-list");
    if (sl) {
      sl.innerHTML = "";
      snippets.forEach((s, i) => renderSnippet(s, i, sl));
    }
    show("snippets-section");
  } else {
    hide("snippets-section");
  }

  if (data.refactor_suggestions) {
    const rc = el("refactor-content");
    if (rc) {
      // Sanitise LLM refactor output too
      rc.innerHTML = safeMarkdown(data.refactor_suggestions);
      rc.querySelectorAll("pre code").forEach(b => hljs.highlightElement(b));
    }
    show("refactor-section");
  } else {
    hide("refactor-section");
  }

  renderTags([]);
  show("tags-row");
  show("panel-answer");
  setTimeout(() => el("panel-answer")?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
}

function renderSnippet(s, idx, container) {
  const score = Math.round((s.score || 0) * 100);
  const lang  = s.language || "text";

  // Build card using DOM APIs — no interpolation of untrusted data into innerHTML
  const card   = document.createElement("div");
  card.className = "snippet-card" + (idx < 2 ? " open" : "");

  const header = document.createElement("div");
  header.className = "snippet-header";

  const scoreEl = document.createElement("span");
  scoreEl.className = "snippet-score";
  scoreEl.textContent = `${score}%`;            // numeric — safe

  const fileEl = document.createElement("span");
  fileEl.className = "snippet-file";
  fileEl.textContent = s.file;                  // textContent — XSS-safe

  const linesEl = document.createElement("span");
  linesEl.className = "snippet-lines";
  linesEl.textContent = `lines ${s.line_start}–${s.line_end}`;  // numeric — safe

  const toggleEl = document.createElement("span");
  toggleEl.className = "snippet-toggle";
  toggleEl.textContent = "▾";

  header.append(scoreEl, fileEl, linesEl, toggleEl);
  header.addEventListener("click", () => card.classList.toggle("open"));

  const body = document.createElement("div");
  body.className = "snippet-body";

  const pre  = document.createElement("pre");
  const code = document.createElement("code");
  code.className = `language-${lang}`;
  code.textContent = s.raw || "";               // textContent — XSS-safe

  pre.appendChild(code);
  body.appendChild(pre);
  card.append(header, body);

  hljs.highlightElement(code);
  container.appendChild(card);
}

// ── Tags ──────────────────────────────────────────────────────────────────────
function renderTags(tags) {
  state.currentTags = [...tags];
  const c = el("tags-container");
  if (!c) return;
  // Clear and rebuild using DOM APIs — no innerHTML with tag text
  while (c.firstChild) c.removeChild(c.firstChild);
  tags.forEach(tag => {
    const pill = document.createElement("span");
    pill.className = "tag-pill";

    const text = document.createTextNode(tag + " ");
    const btn  = document.createElement("button");
    btn.textContent = "×";
    btn.title = "Remove";
    btn.addEventListener("click", () => removeTag(tag));

    pill.append(text, btn);
    c.appendChild(pill);
  });
}

function addTag() {
  const input = el("tag-input");
  if (!input) return;
  const val = input.value.trim().toLowerCase().replace(/\s+/g, "-").slice(0, 32);
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

  while (list.firstChild) list.removeChild(list.firstChild);

  if (!records?.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "No Q&As yet. Ask your first question above!";
    list.appendChild(empty);
    return;
  }

  records.forEach(rec => {
    const item  = document.createElement("div");
    item.className = "history-item";

    // Question — textContent only
    const q = document.createElement("div");
    q.className = "history-item-q";
    q.textContent = rec.question;

    // Meta
    const meta = document.createElement("div");
    meta.className = "history-item-meta";
    const date  = (rec.created_at || "").slice(0, 16).replace("T", " ");
    const count = (rec.snippets || []).length;
    const dateSpan = document.createElement("span");
    dateSpan.textContent = `${date} UTC`;
    const countSpan = document.createElement("span");
    countSpan.textContent = `${count} snippet${count !== 1 ? "s" : ""}`;
    meta.append(dateSpan, countSpan);

    item.append(q, meta);

    // Tags — textContent only
    if (rec.tags?.length) {
      const tagRow = document.createElement("div");
      tagRow.className = "history-item-tags";
      rec.tags.forEach(t => {
        const span = document.createElement("span");
        span.className = "history-tag";
        span.textContent = t;
        tagRow.appendChild(span);
      });
      item.appendChild(tagRow);
    }

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

// ── Session restore ───────────────────────────────────────────────────────────
async function restoreSession() {
  const saved = localStorage.getItem("codelens_session");
  if (!saved) return;
  try {
    const session = await apiFetch(`/api/sessions/${saved}`);
    state.sessionId = saved;

    setText("success-source", session.source || "Previous session");
    const s = session.stats || {};
    setText("success-stats", `${s.files_indexed ?? 0} files · ${s.total_chunks ?? 0} chunks`);

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

// ── Progress helpers ──────────────────────────────────────────────────────────
function setProgress(pct) {
  const bar = el("progress-bar");
  if (bar) bar.style.width = pct + "%";
}

let _progTimer;
function animateProgress(from, to, durationMs) {
  clearInterval(_progTimer);
  const steps = 40, interval = durationMs / steps, increment = (to - from) / steps;
  let current = from;
  setProgress(current);
  _progTimer = setInterval(() => {
    current += increment;
    if (current >= to) { setProgress(to); clearInterval(_progTimer); }
    else setProgress(current);
  }, interval);
}