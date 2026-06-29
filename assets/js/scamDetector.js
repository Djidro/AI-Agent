/**
 * scamDetector.js
 * -----------------------------------------------------------------------
 * Visa-sponsorship detection + lightweight scam/fraud heuristics.
 * Mirrors scripts/scam_detector.py so jobs.json (built server-side) and
 * any client-side recomputation always agree.
 * -----------------------------------------------------------------------
 */

const VISA_KEYWORDS = [
  "visa sponsorship",
  "visa sponsor",
  "employment visa",
  "work permit",
  "relocation assistance",
  "relocation package",
  "sponsored visa",
  "company visa",
];

const SUSPICIOUS_LINK_PATTERNS = [
  /bit\.ly/i,
  /tinyurl/i,
  /wa\.me\/\d+\?text=urgent/i,
  /t\.me\/joinchat/i,
  /\.ru\//i,
  /free-?registration-?fee/i,
];

const SCAM_PHRASES = [
  "registration fee",
  "processing fee required",
  "pay before interview",
  "send money for visa",
  "western union",
  "no interview needed",
  "guaranteed visa",
  "whatsapp only",
];

/** Detect visa-sponsorship language in a job's text fields. */
function detectVisaSponsorship(job) {
  const haystack = `${job.title || ""} ${job.description || ""}`.toLowerCase();
  const matched = VISA_KEYWORDS.filter((kw) => haystack.includes(kw));
  return { detected: matched.length > 0, matchedKeywords: matched };
}

/**
 * Run rule-based scam detection on a job listing.
 * Returns { isSuspicious, reasons[] } — reasons are short, user-facing strings.
 */
function detectScam(job) {
  const reasons = [];
  const haystack = `${job.title || ""} ${job.description || ""}`.toLowerCase();

  // Rule 1: missing company information
  if (!job.company || job.company.trim().length < 2 || /^n\/?a$/i.test(job.company.trim())) {
    reasons.push("Missing or invalid company name");
  }

  // Rule 2: unrealistic salary for entry-level hospitality roles
  const salaryMax = Number(job.salary_max) || Number(job.salary_min) || 0;
  if (salaryMax > 0) {
    if (salaryMax > 15000) {
      reasons.push("Salary unusually high for this role/category");
    }
    if (salaryMax > 0 && salaryMax < 150) {
      reasons.push("Salary unrealistically low — likely a data or listing error");
    }
  }

  // Rule 3: suspicious links
  const url = job.url || "";
  if (SUSPICIOUS_LINK_PATTERNS.some((re) => re.test(url))) {
    reasons.push("Suspicious or shortened application link");
  }
  if (url && !/^https:\/\//i.test(url)) {
    reasons.push("Application link is not secure (https)");
  }

  // Rule 4: known scam phrasing
  const phraseHit = SCAM_PHRASES.find((p) => haystack.includes(p));
  if (phraseHit) {
    reasons.push(`Suspicious phrasing detected: "${phraseHit}"`);
  }

  // Rule 5: description too short / generic to be trustworthy
  if (!job.description || job.description.trim().length < 25) {
    reasons.push("Job description is too short to verify legitimacy");
  }

  return { isSuspicious: reasons.length > 0, reasons };
}

if (typeof window !== "undefined") {
  window.ScamDetector = { detectVisaSponsorship, detectScam, VISA_KEYWORDS };
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { detectVisaSponsorship, detectScam, VISA_KEYWORDS };
}
