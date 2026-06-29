/**
 * dashboard.js
 * -----------------------------------------------------------------------
 * Renders the full dashboard client-side:
 *  - Loads the active agent from localStorage, or from data/agents.json
 *    by Telegram username lookup (the file the bot/Actions write to).
 *  - Fetches data/jobs.json (built by scripts/scraper.py on a schedule).
 *  - Runs dedupe -> scam detection -> visa detection -> AI match scoring
 *    using the exact same shared modules the rest of the project uses.
 *  - Renders stats, the active agent card, latest opportunities, saved
 *    jobs (also localStorage), and a daily report.
 * -----------------------------------------------------------------------
 */
(function () {
  "use strict";

  const SAVED_KEY = "gulfjobs_saved_jobs";
  const AGENT_KEY = "gulfjobs_agent";

  let allJobs = [];
  let scoredJobs = [];
  let agent = null;

  // ---------------------------------------------------------------------
  // Agent loading
  // ---------------------------------------------------------------------
  function loadLocalAgent() {
    try {
      const raw = localStorage.getItem(AGENT_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (err) {
      console.warn("Could not read local agent:", err);
      return null;
    }
  }

  function saveLocalAgent(a) {
    try {
      localStorage.setItem(AGENT_KEY, JSON.stringify(a));
    } catch (err) {
      console.warn("Could not persist agent:", err);
    }
  }

  async function lookupAgentByUsername(username) {
    const clean = username.trim().replace(/^@/, "").toLowerCase();
    if (!clean) return null;
    try {
      const res = await fetch("data/agents.json", { cache: "no-store" });
      if (!res.ok) return null;
      const agents = await res.json();
      const found = (agents || []).find(
        (a) => (a.telegram_username || "").toLowerCase() === clean
      );
      return found || null;
    } catch (err) {
      console.warn("agents.json not reachable:", err);
      return null;
    }
  }

  // ---------------------------------------------------------------------
  // Jobs pipeline: fetch -> dedupe -> scam/visa -> score
  // ---------------------------------------------------------------------
  async function loadJobs() {
    try {
      const res = await fetch("data/jobs.json", { cache: "no-store" });
      if (!res.ok) return [];
      const jobs = await res.json();
      return Array.isArray(jobs) ? jobs : [];
    } catch (err) {
      console.warn("jobs.json not reachable:", err);
      return [];
    }
  }

  function enrichAndScore(jobs, currentAgent) {
    // Duplicate detection (defensive — scraper already dedupes, this guards
    // against any stale/manual edits to jobs.json)
    const deduped = window.Dedupe.dedupeJobs(jobs, []);

    return deduped.map((job) => {
      const visa = window.ScamDetector.detectVisaSponsorship(job);
      const scam = window.ScamDetector.detectScam(job);
      const enriched = {
        ...job,
        visa_sponsorship: job.visa_sponsorship || visa.detected,
        scam_flagged: scam.isSuspicious,
        scam_reasons: scam.reasons,
      };
      if (currentAgent) {
        const { score, breakdown } = window.MatchEngine.computeMatchScore(enriched, currentAgent);
        enriched.match_score = score;
        enriched.match_breakdown = breakdown;
      } else {
        enriched.match_score = null;
      }
      return enriched;
    });
  }

  // ---------------------------------------------------------------------
  // Saved jobs (localStorage)
  // ---------------------------------------------------------------------
  function getSavedIds() {
    try {
      const raw = localStorage.getItem(SAVED_KEY);
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch {
      return new Set();
    }
  }
  function setSavedIds(set) {
    try {
      localStorage.setItem(SAVED_KEY, JSON.stringify(Array.from(set)));
    } catch (err) {
      console.warn("Could not persist saved jobs:", err);
    }
  }
  function toggleSaved(jobId) {
    const set = getSavedIds();
    if (set.has(jobId)) set.delete(jobId);
    else set.add(jobId);
    setSavedIds(set);
    renderAll();
  }

  // ---------------------------------------------------------------------
  // Rendering helpers
  // ---------------------------------------------------------------------
  function scoreClass(score) {
    if (score === null || score === undefined) return "score-low";
    if (score >= 75) return "score-high";
    if (score >= 45) return "score-mid";
    return "score-low";
  }

  function jobRowHtml(job, savedIds) {
    const isSaved = savedIds.has(job.id);
    const score = job.match_score;
    const scoreDisplay = score === null || score === undefined ? "—" : score;
    const badges = [];
    if (job.visa_sponsorship) badges.push('<span class="badge visa">🛂 Visa</span>');
    if (job.accommodation) badges.push('<span class="badge acc">🏠 Accommodation</span>');
    if (job.scam_flagged) badges.push('<span class="badge scam">⚠ Review needed</span>');

    return `
      <div class="job-row" data-job-id="${job.id}">
        <div class="job-score ${scoreClass(score)}">${scoreDisplay}</div>
        <div class="job-main">
          <div class="job-title">${escapeHtml(job.title)} — ${escapeHtml(job.company || "Unknown company")}</div>
          <div class="job-meta">
            <span>📍 ${escapeHtml(job.city ? job.city + ", " : "")}${escapeHtml(job.country)}</span>
            <span>💰 ${job.salary_min || "?"}–${job.salary_max || "?"} ${escapeHtml(job.currency || "USD")}/mo</span>
            <span>🔗 ${escapeHtml(job.source || "Sample dataset")}</span>
          </div>
          <div>${badges.join("")}</div>
        </div>
        <div class="job-actions">
          <button class="btn btn-ghost btn-sm" data-save="${job.id}">${isSaved ? "★ Saved" : "☆ Save"}</button>
          <a class="btn btn-primary btn-sm" href="${escapeAttr(job.url || "#")}" target="_blank" rel="noopener">Apply</a>
        </div>
      </div>`;
  }

  function emptyStateHtml(icon, text) {
    return `<div class="empty-state"><div class="e-icon">${icon}</div><p>${text}</p></div>`;
  }

  function escapeHtml(str) {
    return (str || "").toString().replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }
  function escapeAttr(str) {
    return escapeHtml(str);
  }

  function wireSaveButtons(container) {
    container.querySelectorAll("[data-save]").forEach((btn) => {
      btn.addEventListener("click", () => toggleSaved(btn.getAttribute("data-save")));
    });
  }

  // ---------------------------------------------------------------------
  // Panel renderers
  // ---------------------------------------------------------------------
  function renderAgentCard(targetId, settingsMode) {
    const el = document.getElementById(targetId);
    if (!agent) {
      el.innerHTML = emptyStateHtml("🤖", "No agent configured yet. Create one to start matching jobs.");
      return;
    }
    el.innerHTML = `
      <div class="grid-2">
        <div>
          <p class="hint">Name</p>
          <p style="font-weight:600;">${escapeHtml(agent.name || "—")}</p>
        </div>
        <div>
          <p class="hint">Telegram</p>
          <p style="font-weight:600;">@${escapeHtml(agent.telegram_username || "—")}</p>
        </div>
        <div>
          <p class="hint">Countries</p>
          <p style="font-weight:600;">${(agent.countries || []).join(", ") || "Any"}</p>
        </div>
        <div>
          <p class="hint">Job titles</p>
          <p style="font-weight:600;">${(agent.job_titles || []).join(", ") || "Any"}</p>
        </div>
        <div>
          <p class="hint">Minimum salary</p>
          <p style="font-weight:600;">${agent.min_salary ? "$" + agent.min_salary + "/mo" : "No minimum"}</p>
        </div>
        <div>
          <p class="hint">Requirements</p>
          <p style="font-weight:600;">
            ${agent.visa_required ? "Visa sponsorship · " : ""}${agent.accommodation_required ? "Accommodation" : ""}${!agent.visa_required && !agent.accommodation_required ? "None" : ""}
          </p>
        </div>
      </div>`;
  }

  function renderStats() {
    const total = scoredJobs.length;
    const high = scoredJobs.filter((j) => (j.match_score || 0) >= 75).length;
    const visa = scoredJobs.filter((j) => j.visa_sponsorship).length;
    const saved = getSavedIds().size;
    document.getElementById("statTotal").textContent = total;
    document.getElementById("statHigh").textContent = high;
    document.getElementById("statVisa").textContent = visa;
    document.getElementById("statSaved").textContent = saved;
  }

  function rankedJobs() {
    return [...scoredJobs]
      .filter((j) => !j.scam_flagged)
      .sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
  }

  function renderBestJob(targetId, jobs) {
    const el = document.getElementById(targetId);
    const savedIds = getSavedIds();
    if (jobs.length === 0) {
      el.innerHTML = emptyStateHtml("🌙", "No opportunities yet — the agent scans on its next scheduled run.");
      return;
    }
    el.innerHTML = jobRowHtml(jobs[0], savedIds);
    wireSaveButtons(el);
  }

  function renderMatchesList() {
    const el = document.getElementById("matchesList");
    const countEl = document.getElementById("matchesCount");
    const ranked = rankedJobs();
    countEl.textContent = `${ranked.length} job${ranked.length === 1 ? "" : "s"}`;
    if (ranked.length === 0) {
      el.innerHTML = emptyStateHtml("🔍", "Nothing matches yet. Try widening your countries or roles in agent settings.");
      return;
    }
    const savedIds = getSavedIds();
    el.innerHTML = ranked.map((j) => jobRowHtml(j, savedIds)).join("");
    wireSaveButtons(el);
  }

  function renderSavedList() {
    const el = document.getElementById("savedList");
    const savedIds = getSavedIds();
    const saved = scoredJobs.filter((j) => savedIds.has(j.id));
    if (saved.length === 0) {
      el.innerHTML = emptyStateHtml("⭐", "You haven't saved any jobs yet. Star a listing from Latest Opportunities.");
      return;
    }
    el.innerHTML = saved.map((j) => jobRowHtml(j, savedIds)).join("");
    wireSaveButtons(el);
  }

  function renderReport() {
    const total = scoredJobs.length;
    const high = scoredJobs.filter((j) => (j.match_score || 0) >= 75).length;
    const visaCount = scoredJobs.filter((j) => j.visa_sponsorship).length;
    const scamCount = scoredJobs.filter((j) => j.scam_flagged).length;
    document.getElementById("repTotal").textContent = total;
    document.getElementById("repHigh").textContent = high;
    document.getElementById("repVisa").textContent = visaCount;
    document.getElementById("repScam").textContent = scamCount;
    renderBestJob("repBestSlot", rankedJobs());
  }

  function renderAll() {
    renderStats();
    renderAgentCard("agentDetails", false);
    renderAgentCard("agentSettingsDetails", true);
    renderBestJob("bestJobSlot", rankedJobs());
    renderMatchesList();
    renderSavedList();
    renderReport();

    const summary = document.getElementById("agentSummaryLine");
    const greeting = document.getElementById("greeting");
    if (agent) {
      greeting.textContent = `Welcome back, ${agent.name || "there"}`;
      summary.textContent = `Tracking ${(agent.countries || []).join(", ") || "all countries"} · ${(agent.job_titles || []).join(", ") || "all roles"}`;
    } else {
      greeting.textContent = "Your dashboard";
      summary.textContent = "No agent loaded — create one or load it by Telegram username below.";
    }

    document.getElementById("noAgentBanner").hidden = !!agent;
  }

  // ---------------------------------------------------------------------
  // Sidebar panel switching
  // ---------------------------------------------------------------------
  function wireSidebar() {
    const links = document.querySelectorAll(".side-link");
    const panels = document.querySelectorAll(".dash-panel");
    links.forEach((link) => {
      link.addEventListener("click", () => {
        const target = link.getAttribute("data-panel");
        links.forEach((l) => l.classList.toggle("active", l === link));
        panels.forEach((p) => {
          p.hidden = p.getAttribute("data-panel") !== target;
        });
      });
    });
  }

  function wireLookup() {
    const btn = document.getElementById("lookupBtn");
    const input = document.getElementById("lookupUsername");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Loading…";
      const found = await lookupAgentByUsername(input.value);
      btn.disabled = false;
      btn.textContent = "Load agent";
      if (found) {
        agent = found;
        saveLocalAgent(found);
        scoredJobs = enrichAndScore(allJobs, agent);
        renderAll();
      } else {
        alert("No agent found for that Telegram username yet. Make sure you've messaged the bot and tapped Start.");
      }
    });
  }

  function wireMisc() {
    document.getElementById("refreshBtn").addEventListener("click", async () => {
      allJobs = await loadJobs();
      scoredJobs = enrichAndScore(allJobs, agent);
      renderAll();
    });
    document.getElementById("clearAgentBtn").addEventListener("click", () => {
      if (!confirm("Remove this agent from the current device? (Your Telegram registration stays active.)")) return;
      localStorage.removeItem(AGENT_KEY);
      agent = null;
      scoredJobs = enrichAndScore(allJobs, null);
      renderAll();
    });
  }

  // ---------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------
  async function init() {
    wireSidebar();
    wireLookup();
    wireMisc();

    agent = loadLocalAgent();
    allJobs = await loadJobs();
    scoredJobs = enrichAndScore(allJobs, agent);
    renderAll();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
