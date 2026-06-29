"""
scripts/scam_detector.py
-----------------------------------------------------------------------
Visa-sponsorship detection + lightweight scam/fraud heuristics.
Direct port of assets/js/scamDetector.js — keep both in sync.
-----------------------------------------------------------------------
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Tuple

VISA_KEYWORDS = [
    "visa sponsorship",
    "visa sponsor",
    "employment visa",
    "work permit",
    "relocation assistance",
    "relocation package",
    "sponsored visa",
    "company visa",
]

SUSPICIOUS_LINK_PATTERNS = [
    re.compile(r"bit\.ly", re.I),
    re.compile(r"tinyurl", re.I),
    re.compile(r"wa\.me/\d+\?text=urgent", re.I),
    re.compile(r"t\.me/joinchat", re.I),
    re.compile(r"\.ru/", re.I),
    re.compile(r"free-?registration-?fee", re.I),
]

SCAM_PHRASES = [
    "registration fee",
    "processing fee required",
    "pay before interview",
    "send money for visa",
    "western union",
    "no interview needed",
    "guaranteed visa",
    "whatsapp only",
]


def detect_visa_sponsorship(job: Dict[str, Any]) -> Dict[str, Any]:
    haystack = f"{job.get('title', '')} {job.get('description', '')}".lower()
    matched = [kw for kw in VISA_KEYWORDS if kw in haystack]
    return {"detected": len(matched) > 0, "matchedKeywords": matched}


def detect_scam(job: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    haystack = f"{job.get('title', '')} {job.get('description', '')}".lower()

    company = (job.get("company") or "").strip()
    if len(company) < 2 or re.match(r"^n/?a$", company, re.I):
        reasons.append("Missing or invalid company name")

    salary_max = float(job.get("salary_max") or job.get("salary_min") or 0)
    if salary_max > 0:
        if salary_max > 15000:
            reasons.append("Salary unusually high for this role/category")
        if 0 < salary_max < 150:
            reasons.append("Salary unrealistically low — likely a data or listing error")

    url = job.get("url") or ""
    if any(pattern.search(url) for pattern in SUSPICIOUS_LINK_PATTERNS):
        reasons.append("Suspicious or shortened application link")
    if url and not re.match(r"^https://", url, re.I):
        reasons.append("Application link is not secure (https)")

    phrase_hit = next((p for p in SCAM_PHRASES if p in haystack), None)
    if phrase_hit:
        reasons.append(f'Suspicious phrasing detected: "{phrase_hit}"')

    description = (job.get("description") or "").strip()
    if len(description) < 25:
        reasons.append("Job description is too short to verify legitimacy")

    return {"isSuspicious": len(reasons) > 0, "reasons": reasons}
