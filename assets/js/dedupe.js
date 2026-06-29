/**
 * dedupe.js
 * -----------------------------------------------------------------------
 * Duplicate detection. A job is considered the same listing if its
 * normalized (title + company + country + source) signature repeats,
 * regardless of how the source re-formats whitespace/case on re-scrape.
 * Mirrors the hashing approach in scripts/scraper.py so ids stay stable
 * between the Python scraper and any client-side recomputation.
 * -----------------------------------------------------------------------
 */

/** Simple, stable 32-bit string hash (djb2 variant) -> hex string. */
function hashString(str) {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 33) ^ str.charCodeAt(i);
  }
  // Force unsigned and to hex
  return (hash >>> 0).toString(16);
}

/** Build the canonical signature used to detect duplicate listings. */
function jobSignature(job) {
  return [job.title, job.company, job.country, job.source]
    .map((v) => (v || "").toString().trim().toLowerCase().replace(/\s+/g, " "))
    .join("|");
}

/** Deterministic job id derived from its signature. */
function generateJobId(job) {
  return `job_${hashString(jobSignature(job))}`;
}

/**
 * Filter out jobs whose id already exists in `existingIds` (a Set or Array).
 * Returns only genuinely new jobs, in original order.
 */
function dedupeJobs(jobs, existingIds) {
  const seen = new Set(existingIds instanceof Set ? existingIds : existingIds || []);
  const result = [];
  for (const job of jobs) {
    const id = job.id || generateJobId(job);
    if (seen.has(id)) continue;
    seen.add(id);
    result.push({ ...job, id });
  }
  return result;
}

if (typeof window !== "undefined") {
  window.Dedupe = { hashString, jobSignature, generateJobId, dedupeJobs };
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { hashString, jobSignature, generateJobId, dedupeJobs };
}
