/**
 * create-agent.js
 * -----------------------------------------------------------------------
 * Drives the 3-step "Create Job Agent" form.
 *
 * Persistence model (no backend server):
 *   1. The full preference profile is saved to localStorage so THIS browser's
 *      dashboard can render immediately.
 *   2. A compact preference payload is base64url-encoded into a Telegram
 *      deep link (t.me/<bot>?start=<payload>). When the user taps it, the
 *      bot (scripts/telegram_bot.py) decodes it and writes the agent into
 *      data/agents.json via the next GitHub Actions run — that JSON file is
 *      the real source of truth the notifier/dashboard use across devices.
 *   3. If the encoded payload would exceed Telegram's 64-character start
 *      parameter limit (e.g. many countries/titles picked), we fall back to
 *      a plain `?start=setup` link and the bot runs a short conversational
 *      onboarding instead — so registration always works either way.
 * -----------------------------------------------------------------------
 */
(function () {
  "use strict";

  // Replace with your real bot username once you create it (see docs/TELEGRAM_BOT_GUIDE.md)
  const BOT_USERNAME = "GulfJobsAIBot";

  const COUNTRY_CODES = {
    UAE: "UAE",
    Qatar: "QAT",
    Oman: "OMN",
    "Saudi Arabia": "SAU",
    Kuwait: "KWT",
    Bahrain: "BHR",
  };
  const TITLE_CODES = {
    Barista: "BAR",
    Waiter: "WAI",
    "Hotel Staff": "HOT",
    Hospitality: "HSP",
    "Customer Service": "CUS",
  };

  const form = document.getElementById("agentForm");
  const steps = Array.from(form.querySelectorAll(".form-step"));
  const progressDots = Array.from(document.querySelectorAll("#progressBar span"));
  let currentStep = 1;

  function showStep(step) {
    steps.forEach((s) => {
      s.hidden = s.dataset.step !== String(step);
    });
    progressDots.forEach((d) => {
      d.classList.toggle("active", Number(d.dataset.step) <= step && step <= 3);
    });
    currentStep = step;
  }

  function setError(fieldEl, show) {
    if (!fieldEl) return;
    fieldEl.classList.toggle("has-error", show);
  }

  function validateStep1() {
    let ok = true;
    const name = document.getElementById("name").value.trim();
    const telegram = document.getElementById("telegram").value.trim();
    const nameField = document.getElementById("field-name");
    const tgField = document.getElementById("field-telegram");

    if (name.length < 2) {
      setError(nameField, true);
      ok = false;
    } else {
      setError(nameField, false);
    }

    const tgPattern = /^@?[a-zA-Z0-9_]{5,32}$/;
    if (!tgPattern.test(telegram)) {
      setError(tgField, true);
      ok = false;
    } else {
      setError(tgField, false);
    }
    return ok;
  }

  function validateStep2() {
    let ok = true;
    const countries = form.querySelectorAll('input[name="countries"]:checked');
    const titles = form.querySelectorAll('input[name="titles"]:checked');
    const countryErr = document.getElementById("err-countries");
    const titleErr = document.getElementById("err-titles");

    countryErr.style.display = countries.length === 0 ? "block" : "none";
    titleErr.style.display = titles.length === 0 ? "block" : "none";

    if (countries.length === 0) ok = false;
    if (titles.length === 0) ok = false;
    return ok;
  }

  form.addEventListener("click", (e) => {
    const action = e.target.getAttribute("data-action");
    if (!action) return;

    if (action === "next") {
      if (currentStep === 1 && !validateStep1()) return;
      if (currentStep === 2 && !validateStep2()) return;
      showStep(currentStep + 1);
    }
    if (action === "back") {
      showStep(currentStep - 1);
    }
  });

  /** djb2 hash, base64url-safe encode helper shared in spirit with dedupe.js */
  function base64url(str) {
    const b64 = btoa(unescape(encodeURIComponent(str)));
    return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function buildAgentProfile() {
    const countries = Array.from(form.querySelectorAll('input[name="countries"]:checked')).map((el) => el.value);
    const titles = Array.from(form.querySelectorAll('input[name="titles"]:checked')).map((el) => el.value);
    return {
      name: document.getElementById("name").value.trim(),
      telegram_username: document.getElementById("telegram").value.trim().replace(/^@/, ""),
      countries,
      job_titles: titles,
      min_salary: Number(document.getElementById("salary").value) || 0,
      visa_required: document.getElementById("visaRequired").checked,
      accommodation_required: document.getElementById("accommodationRequired").checked,
      created_at: new Date().toISOString(),
    };
  }

  function buildDeepLink(agent) {
    const cCodes = agent.countries.map((c) => COUNTRY_CODES[c]).filter(Boolean).join(",");
    const tCodes = agent.job_titles.map((t) => TITLE_CODES[t]).filter(Boolean).join(",");
    const raw = `v1|C:${cCodes}|J:${tCodes}|S:${agent.min_salary}|VS:${agent.visa_required ? 1 : 0}|AC:${agent.accommodation_required ? 1 : 0}`;
    const payload = base64url(raw);

    // Telegram start parameters must be <= 64 chars and match [A-Za-z0-9_-]+
    if (payload.length <= 64) {
      return `https://t.me/${BOT_USERNAME}?start=${payload}`;
    }
    // Fallback: bot will ask the questions conversationally instead.
    return `https://t.me/${BOT_USERNAME}?start=setup`;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!validateStep1() || !validateStep2()) {
      // Jump back to whichever step is invalid
      if (!validateStep1()) showStep(1);
      else showStep(2);
      return;
    }

    const agent = buildAgentProfile();

    try {
      localStorage.setItem("gulfjobs_agent", JSON.stringify(agent));
    } catch (err) {
      console.warn("Could not save to localStorage:", err);
    }

    const link = buildDeepLink(agent);
    const linkEl = document.getElementById("telegramDeepLink");
    const codeEl = document.getElementById("deeplinkText");
    linkEl.setAttribute("href", link);
    codeEl.textContent = link;

    showStep("success");
  });
})();
