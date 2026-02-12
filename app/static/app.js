/* ═══════════════════════════════════════════════════════════════════════════
   AI Summary — Frontend Application
   ═══════════════════════════════════════════════════════════════════════════ */

(() => {
  "use strict";

  // ── State ──────────────────────────────────────────────────────────────
  let apiKey = localStorage.getItem("api_key") || "";
  let username = localStorage.getItem("username") || "";
  let currentJobId = null;
  let pollTimer = null;
  let currentTab = "youtube"; // youtube | upload
  let authMode = "login";     // login | register

  // ── DOM refs ───────────────────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const authScreen = $("#auth-screen");
  const appScreen = $("#app-screen");
  const authForm = $("#auth-form");
  const authError = $("#auth-error");
  const authSubmit = $("#auth-submit");
  const authUser = $("#auth-username");
  const authPass = $("#auth-password");

  const userLabel = $("#user-label");
  const logoutBtn = $("#logout-btn");

  const ytUrl = $("#yt-url");
  const fileInput = $("#file-input");
  const dropZone = $("#drop-zone");
  const fileName = $("#file-name");
  const maxSizeHint = $("#max-size-hint");
  const startBtn = $("#start-btn");

  const jobCard = $("#job-card");
  const jobIdLabel = $("#job-id-label");
  const jobStatusLabel = $("#job-status-label");
  const progressFill = $("#progress-fill");
  const progressText = $("#progress-text");

  const errorCard = $("#error-card");
  const errorMessage = $("#error-message");

  const resultCard = $("#result-card");
  const tldrText = $("#tldr-text");
  const keypointsList = $("#keypoints-list");
  const outlineContent = $("#outline-content");
  const actionsList = $("#actions-list");
  const timestampsList = $("#timestamps-list");
  const transcriptText = $("#transcript-text");
  const transcriptToggle = $("#transcript-toggle");
  const transcriptBody = $("#transcript-body");

  const historyList = $("#history-list");
  const emptyHistory = $("#empty-history");

  let lastResult = null;
  let lastSource = null;

  // ── Init ────────────────────────────────────────────────────────────────
  function init() {
    if (apiKey) {
      showApp();
    } else {
      showAuth();
    }

    setupTabs();
    setupSegControls();
    setupAuth();
    setupDropZone();
    setupStartBtn();
    setupResultActions();
    loadHistory();
    fetchConfig();
  }

  // ── Auth ────────────────────────────────────────────────────────────────
  function showAuth() {
    authScreen.classList.remove("hidden");
    appScreen.classList.add("hidden");
  }

  function showApp() {
    authScreen.classList.add("hidden");
    appScreen.classList.remove("hidden");
    userLabel.textContent = username;
  }

  function setupAuth() {
    // Auth tabs
    $$(".auth-tabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$(".auth-tabs .tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        authMode = tab.dataset.tab;
        authSubmit.textContent = authMode === "login" ? "Login" : "Register";
        authError.classList.add("hidden");
      });
    });

    authForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      authError.classList.add("hidden");
      authSubmit.disabled = true;
      authSubmit.textContent = "...";

      try {
        const endpoint = authMode === "login" ? "/v1/auth/login" : "/v1/auth/register";
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: authUser.value.trim(),
            password: authPass.value,
          }),
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Authentication failed");
        }

        apiKey = data.api_key;
        username = data.username;
        localStorage.setItem("api_key", apiKey);
        localStorage.setItem("username", username);
        showApp();
      } catch (err) {
        authError.textContent = err.message;
        authError.classList.remove("hidden");
      } finally {
        authSubmit.disabled = false;
        authSubmit.textContent = authMode === "login" ? "Login" : "Register";
      }
    });

    logoutBtn.addEventListener("click", () => {
      apiKey = "";
      username = "";
      localStorage.removeItem("api_key");
      localStorage.removeItem("username");
      showAuth();
    });
  }

  // ── Tabs ────────────────────────────────────────────────────────────────
  function setupTabs() {
    $$(".input-tabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$(".input-tabs .tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        currentTab = tab.dataset.tab;
        $("#panel-youtube").classList.toggle("hidden", currentTab !== "youtube");
        $("#panel-upload").classList.toggle("hidden", currentTab !== "upload");
      });
    });
  }

  // ── Segmented Controls ─────────────────────────────────────────────────
  function setupSegControls() {
    [$("#style-control"), $("#lang-control")].forEach((ctrl) => {
      ctrl.querySelectorAll(".seg").forEach((seg) => {
        seg.addEventListener("click", () => {
          ctrl.querySelectorAll(".seg").forEach((s) => s.classList.remove("active"));
          seg.classList.add("active");
        });
      });
    });
  }

  function getStyle() {
    return $("#style-control .seg.active")?.dataset.val || "medium";
  }

  function getLang() {
    return $("#lang-control .seg.active")?.dataset.val || "auto";
  }

  // ── Drop Zone ──────────────────────────────────────────────────────────
  function setupDropZone() {
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });
    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("dragover");
    });
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        showFileName(e.dataTransfer.files[0].name);
      }
    });
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) {
        showFileName(fileInput.files[0].name);
      }
    });
  }

  function showFileName(name) {
    fileName.textContent = name;
    fileName.classList.remove("hidden");
    $$(".drop-text").forEach((t) => t.classList.add("hidden"));
  }

  // ── Config ─────────────────────────────────────────────────────────────
  async function fetchConfig() {
    try {
      const res = await apiFetch("/v1/jobs/config");
      if (res.ok) {
        const data = await res.json();
        maxSizeHint.textContent = `(max ${data.max_upload_mb} MB)`;
      }
    } catch {}
  }

  // ── Start Processing ──────────────────────────────────────────────────
  function setupStartBtn() {
    startBtn.addEventListener("click", async () => {
      hideCards();
      startBtn.disabled = true;
      startBtn.textContent = "Processing...";

      try {
        let res;
        if (currentTab === "youtube") {
          const url = ytUrl.value.trim();
          if (!url) throw new Error("Please enter a YouTube URL");

          res = await apiFetch("/v1/youtube", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              url,
              summary_style: getStyle(),
              language: getLang(),
            }),
          });
        } else {
          if (!fileInput.files.length) throw new Error("Please select a file");

          const formData = new FormData();
          formData.append("file", fileInput.files[0]);
          formData.append("summary_style", getStyle());
          formData.append("language", getLang());

          res = await apiFetch("/v1/upload", {
            method: "POST",
            body: formData,
          });
        }

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Request failed");

        currentJobId = data.job_id;
        showJobCard(data.job_id, data.status, 0);
        startPolling(data.job_id);

      } catch (err) {
        showError(err.message);
      } finally {
        startBtn.disabled = false;
        startBtn.textContent = "▶ Start Processing";
      }
    });
  }

  // ── Polling ────────────────────────────────────────────────────────────
  function startPolling(jobId) {
    stopPolling();
    pollTimer = setInterval(() => pollJob(jobId), 2000);
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  async function pollJob(jobId) {
    try {
      const res = await apiFetch(`/v1/jobs/${jobId}`);
      if (!res.ok) {
        stopPolling();
        showError("Failed to fetch job status");
        return;
      }
      const data = await res.json();
      showJobCard(jobId, data.status, data.progress);

      if (data.status === "done") {
        stopPolling();
        await fetchResult(jobId, data.source_meta);
      } else if (data.status === "error") {
        stopPolling();
        const msg = data.error?.message || "Processing failed";
        showError(msg);
      }
    } catch (err) {
      stopPolling();
      showError("Connection error: " + err.message);
    }
  }

  async function fetchResult(jobId, sourceMeta) {
    try {
      const res = await apiFetch(`/v1/jobs/${jobId}/result`);
      if (!res.ok) throw new Error("Failed to fetch result");
      const data = await res.json();

      lastResult = data;
      lastSource = sourceMeta;
      renderResult(data, sourceMeta);
      saveHistory(jobId, sourceMeta);
    } catch (err) {
      showError(err.message);
    }
  }

  // ── UI Helpers ─────────────────────────────────────────────────────────
  function hideCards() {
    jobCard.classList.add("hidden");
    errorCard.classList.add("hidden");
    resultCard.classList.add("hidden");
  }

  function showJobCard(jobId, status, progress) {
    jobCard.classList.remove("hidden");
    jobIdLabel.textContent = jobId.substring(0, 8) + "...";
    jobStatusLabel.textContent = status;
    jobStatusLabel.className = "job-status " + status;
    progressFill.style.width = progress + "%";
    progressText.textContent = progress + "%";
  }

  function showError(msg) {
    errorCard.classList.remove("hidden");
    errorMessage.textContent = msg;
  }

  // ── Render Result ──────────────────────────────────────────────────────
  function renderResult(data, sourceMeta) {
    resultCard.classList.remove("hidden");
    const s = data.summary || {};

    // TL;DR
    tldrText.textContent = s.tl_dr || "—";
    $("#section-tldr").classList.toggle("hidden", !s.tl_dr);

    // Key Points
    keypointsList.innerHTML = "";
    (s.key_points || []).forEach((kp) => {
      const li = document.createElement("li");
      li.textContent = kp;
      keypointsList.appendChild(li);
    });
    $("#section-keypoints").classList.toggle("hidden", !(s.key_points?.length));

    // Outline
    outlineContent.innerHTML = "";
    (s.outline || []).forEach((sec) => {
      const block = document.createElement("div");
      block.className = "outline-block";
      const h4 = document.createElement("h4");
      h4.textContent = sec.title || sec;
      block.appendChild(h4);
      if (sec.points && sec.points.length) {
        const ul = document.createElement("ul");
        sec.points.forEach((p) => {
          const li = document.createElement("li");
          li.textContent = p;
          ul.appendChild(li);
        });
        block.appendChild(ul);
      }
      outlineContent.appendChild(block);
    });
    $("#section-outline").classList.toggle("hidden", !(s.outline?.length));

    // Action Items
    actionsList.innerHTML = "";
    (s.action_items || []).forEach((ai) => {
      const li = document.createElement("li");
      li.textContent = ai;
      actionsList.appendChild(li);
    });
    $("#section-actions").classList.toggle("hidden", !(s.action_items?.length));

    // Timestamps
    timestampsList.innerHTML = "";
    const videoId = sourceMeta?.video_id;
    (s.timestamps || []).forEach((ts) => {
      const div = document.createElement("div");
      div.className = "ts-item";

      const timeSpan = document.createElement("span");
      timeSpan.className = "ts-time";
      timeSpan.textContent = ts.t;

      const labelSpan = document.createElement("span");
      labelSpan.className = "ts-label";
      labelSpan.textContent = ts.label;

      div.appendChild(timeSpan);
      div.appendChild(labelSpan);

      if (videoId) {
        div.addEventListener("click", () => {
          const secs = hmsToSeconds(ts.t);
          window.open(`https://www.youtube.com/watch?v=${videoId}&t=${secs}`, "_blank");
        });
      }

      timestampsList.appendChild(div);
    });
    $("#section-timestamps").classList.toggle("hidden", !(s.timestamps?.length));

    // Transcript
    const tr = data.transcript || {};
    transcriptText.textContent = tr.text || "—";
    transcriptBody.classList.add("hidden");
    transcriptToggle.classList.remove("open");

    transcriptToggle.onclick = () => {
      transcriptBody.classList.toggle("hidden");
      transcriptToggle.classList.toggle("open");
    };
  }

  function hmsToSeconds(hms) {
    const parts = hms.split(":").map(Number);
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    return parts[0] || 0;
  }

  // ── Result Actions ─────────────────────────────────────────────────────
  function setupResultActions() {
    $("#copy-summary-btn").addEventListener("click", () => {
      if (!lastResult?.summary) return;
      const s = lastResult.summary;
      let text = `TL;DR: ${s.tl_dr || ""}\n\n`;
      text += `Key Points:\n${(s.key_points || []).map((p) => "• " + p).join("\n")}\n\n`;
      if (s.outline?.length) {
        text += `Outline:\n${s.outline.map((o) => `${o.title || o}\n${(o.points || []).map((p) => "  - " + p).join("\n")}`).join("\n\n")}\n\n`;
      }
      if (s.action_items?.length) {
        text += `Action Items:\n${s.action_items.map((a) => "☐ " + a).join("\n")}\n`;
      }
      copyToClipboard(text);
      toast("Summary copied!", "success");
    });

    $("#copy-transcript-btn").addEventListener("click", () => {
      if (!lastResult?.transcript?.text) return;
      copyToClipboard(lastResult.transcript.text);
      toast("Transcript copied!", "success");
    });

    $("#download-json-btn").addEventListener("click", () => {
      if (!lastResult) return;
      const blob = new Blob([JSON.stringify(lastResult, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "ai-summary-result.json";
      a.click();
      URL.revokeObjectURL(url);
      toast("JSON downloaded!", "success");
    });
  }

  function copyToClipboard(text) {
    navigator.clipboard.writeText(text).catch(() => {
      // Fallback
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    });
  }

  // ── History ────────────────────────────────────────────────────────────
  function getHistory() {
    try {
      return JSON.parse(localStorage.getItem("job_history") || "[]");
    } catch {
      return [];
    }
  }

  function saveHistory(jobId, sourceMeta) {
    let history = getHistory();
    const entry = {
      job_id: jobId,
      source: sourceMeta?.title || sourceMeta?.filename || sourceMeta?.url || "Unknown",
      type: sourceMeta?.video_id ? "youtube" : "upload",
      created_at: new Date().toISOString(),
    };
    // Deduplicate
    history = history.filter((h) => h.job_id !== jobId);
    history.unshift(entry);
    history = history.slice(0, 5);
    localStorage.setItem("job_history", JSON.stringify(history));
    loadHistory();
  }

  function loadHistory() {
    const history = getHistory();
    historyList.innerHTML = "";

    if (!history.length) {
      emptyHistory.classList.remove("hidden");
      return;
    }
    emptyHistory.classList.add("hidden");

    history.forEach((h) => {
      const div = document.createElement("div");
      div.className = "history-item";

      const src = document.createElement("span");
      src.className = "history-source";
      src.textContent = h.source;

      const meta = document.createElement("span");
      meta.className = "history-meta";
      meta.innerHTML = `<span>${h.type}</span><span>${timeAgo(h.created_at)}</span>`;

      div.appendChild(src);
      div.appendChild(meta);

      div.addEventListener("click", async () => {
        hideCards();
        try {
          // First check status
          const statusRes = await apiFetch(`/v1/jobs/${h.job_id}`);
          if (!statusRes.ok) throw new Error("Job not found");
          const statusData = await statusRes.json();

          if (statusData.status === "done") {
            showJobCard(h.job_id, "done", 100);
            await fetchResult(h.job_id, statusData.source_meta);
          } else if (statusData.status === "error") {
            showJobCard(h.job_id, "error", statusData.progress);
            showError(statusData.error?.message || "Processing failed");
          } else {
            showJobCard(h.job_id, statusData.status, statusData.progress);
            startPolling(h.job_id);
          }
        } catch (err) {
          showError(err.message);
        }
      });

      historyList.appendChild(div);
    });
  }

  function timeAgo(iso) {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  }

  // ── Toast ──────────────────────────────────────────────────────────────
  function toast(msg, type = "") {
    const el = $("#toast");
    el.textContent = msg;
    el.className = "toast " + type;
    setTimeout(() => el.classList.add("hidden"), 2500);
  }

  // ── API Fetch Wrapper ──────────────────────────────────────────────────
  function apiFetch(url, opts = {}) {
    opts.headers = opts.headers || {};
    if (apiKey) {
      opts.headers["X-API-Key"] = apiKey;
    }
    return fetch(url, opts);
  }

  // ── Boot ───────────────────────────────────────────────────────────────
  init();
})();
