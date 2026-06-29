/**
 * matchEngine.js
 * -----------------------------------------------------------------------
 * AI Match Score engine for GulfJobs AI Agent.
 * Pure functions, no DOM access, so the exact same scoring logic can be
 * unit-tested, reused on the dashboard, and mirrored in scripts/match_engine.py
 * for the server-side (GitHub Actions) notifier.
 *
 * Score breakdown (0-100):
 *   Country match        25 pts
 *   Job title match       30 pts
 *   Salary fit            20 pts
 *   Visa sponsorship      15 pts
 *   Accommodation         10 pts
 * -----------------------------------------------------------------------
 */

const WEIGHTS = {
  country: 25,
  title: 30,
  salary: 20,
  visa: 15,
  accommodation: 10,
};

/** Normalize a string for loose comparison. */
function norm(str) {
  return (str || "").toString().toLowerCase().trim();
}

/** Tokenize a job-title style string into comparable keyword tokens. */
function titleTokens(str) {
  return norm(str)
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length > 1);
}

/**
 * Score how well a job's country matches the agent's preferred countries.
 * Returns a fraction 0..1.
 */
function scoreCountry(job, agent) {
  if (!agent.countries || agent.countries.length === 0) return 0.5; // no preference = neutral
  const jobCountry = norm(job.country);
  const match = agent.countries.some((c) => norm(c) === jobCountry);
  return match ? 1 : 0;
}

/**
 * Score job-title relevance using token overlap between the agent's
 * preferred titles and the job title (+ a light boost from the description).
 */
function scoreTitle(job, agent) {
  if (!agent.job_titles || agent.job_titles.length === 0) return 0.5;
  const jobTitleTokens = new Set(titleTokens(job.title));
  const jobDescTokens = new Set(titleTokens(job.description || ""));

  let best = 0;
  for (const pref of agent.job_titles) {
    const prefTokens = titleTokens(pref);
    if (prefTokens.length === 0) continue;
    let overlap = 0;
    for (const t of prefTokens) {
      if (jobTitleTokens.has(t)) overlap += 1;
      else if (jobDescTokens.has(t)) overlap += 0.5;
    }
    const ratio = overlap / prefTokens.length;
    if (ratio > best) best = ratio;
  }
  return Math.min(best, 1);
}

/**
 * Score salary fit: 1.0 if job meets/exceeds the agent's minimum,
 * partial credit on a sliding scale if it's close but under.
 */
function scoreSalary(job, agent) {
  const min = Number(agent.min_salary) || 0;
  if (min <= 0) return 1; // no requirement set
  const jobMax = Number(job.salary_max) || Number(job.salary_min) || 0;
  if (jobMax <= 0) return 0.3; // salary not disclosed -> some uncertainty penalty
  if (jobMax >= min) return 1;
  const ratio = jobMax / min;
  return Math.max(0, ratio - 0.15); // soft falloff below requirement
}

/** Score visa sponsorship requirement match. */
function scoreVisa(job, agent) {
  if (!agent.visa_required) return 1; // not required -> full credit either way
  return job.visa_sponsorship ? 1 : 0;
}

/** Score accommodation requirement match. */
function scoreAccommodation(job, agent) {
  if (!agent.accommodation_required) return 1;
  return job.accommodation ? 1 : 0;
}

/**
 * Compute the full AI Match Score (0-100, integer) for a job against
 * an agent's preferences, plus the per-factor breakdown for transparency.
 */
function computeMatchScore(job, agent) {
  const breakdown = {
    country: scoreCountry(job, agent) * WEIGHTS.country,
    title: scoreTitle(job, agent) * WEIGHTS.title,
    salary: scoreSalary(job, agent) * WEIGHTS.salary,
    visa: scoreVisa(job, agent) * WEIGHTS.visa,
    accommodation: scoreAccommodation(job, agent) * WEIGHTS.accommodation,
  };
  const total = Object.values(breakdown).reduce((a, b) => a + b, 0);
  return {
    score: Math.round(Math.max(0, Math.min(100, total))),
    breakdown,
  };
}

/** Bucket a numeric score into a label used for badge styling. */
function scoreLabel(score) {
  if (score >= 75) return "high";
  if (score >= 45) return "mid";
  return "low";
}

// Expose for both <script> tag usage (browser global) and potential bundling.
if (typeof window !== "undefined") {
  window.MatchEngine = { computeMatchScore, scoreLabel, WEIGHTS };
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { computeMatchScore, scoreLabel, WEIGHTS };
}
