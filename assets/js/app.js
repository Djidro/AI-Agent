/**
 * app.js — landing page (index.html) behaviour.
 * No frameworks: vanilla JS only, per project requirements.
 */
(function () {
  "use strict";

  // Footer year
  document.querySelectorAll("[data-year]").forEach((el) => {
    el.textContent = new Date().getFullYear();
  });

  // Smooth-scroll for in-page anchor links (nav + CTA buttons)
  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", (e) => {
      const targetId = link.getAttribute("href");
      if (targetId.length <= 1) return;
      const target = document.querySelector(targetId);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  // Highlight whether an agent already exists in this browser, and adjust
  // primary CTAs to go straight to the dashboard instead of the create flow.
  try {
    const existing = localStorage.getItem("gulfjobs_agent");
    if (existing) {
      document.querySelectorAll('[data-cta="primary"]').forEach((btn) => {
        btn.setAttribute("href", "dashboard.html");
        btn.textContent = "Go to dashboard";
      });
    }
  } catch (err) {
    // localStorage unavailable (privacy mode) — fail silently, default CTAs stand.
    console.warn("Storage unavailable:", err);
  }

  // Live counters in hero-meta, purely illustrative client-side animation
  // pulling from the static sample dataset size so the number is real.
  fetch("data/jobs.json")
    .then((res) => (res.ok ? res.json() : []))
    .then((jobs) => {
      const counter = document.querySelector("[data-live-jobs]");
      if (counter && Array.isArray(jobs)) {
        counter.textContent = jobs.length;
      }
    })
    .catch(() => {
      /* offline or first load before Actions has run — keep static fallback text */
    });
})();
