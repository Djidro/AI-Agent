"""
scripts/match_engine.py
-----------------------------------------------------------------------
Server-side AI Match Score engine. This is a direct, line-for-line port
of assets/js/matchEngine.js so that the dashboard (client-side) and the
Telegram bot / GitHub Actions notifier (server-side) always agree on a
job's score. If you change the weighting here, change it there too.

Score breakdown (0-100):
  Country match        25 pts
  Job title match       30 pts
  Salary fit            20 pts
  Visa sponsorship      15 pts
  Accommodation         10 pts
-----------------------------------------------------------------------
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Tuple

WEIGHTS = {
    "country": 25,
    "title": 30,
    "salary": 20,
    "visa": 15,
    "accommodation": 10,
}


def _norm(s: Any) -> str:
    return (str(s) if s is not None else "").lower().strip()


def _title_tokens(s: Any) -> List[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", _norm(s))
    return [t for t in cleaned.split() if len(t) > 1]


def score_country(job: Dict[str, Any], agent: Dict[str, Any]) -> float:
    countries = agent.get("countries") or []
    if not countries:
        return 0.5  # no preference set -> neutral score
    job_country = _norm(job.get("country"))
    return 1.0 if any(_norm(c) == job_country for c in countries) else 0.0


def score_title(job: Dict[str, Any], agent: Dict[str, Any]) -> float:
    prefs = agent.get("job_titles") or []
    if not prefs:
        return 0.5
    job_title_tokens = set(_title_tokens(job.get("title")))
    job_desc_tokens = set(_title_tokens(job.get("description") or ""))

    best = 0.0
    for pref in prefs:
        pref_tokens = _title_tokens(pref)
        if not pref_tokens:
            continue
        overlap = 0.0
        for t in pref_tokens:
            if t in job_title_tokens:
                overlap += 1
            elif t in job_desc_tokens:
                overlap += 0.5
        ratio = overlap / len(pref_tokens)
        best = max(best, ratio)
    return min(best, 1.0)


def score_salary(job: Dict[str, Any], agent: Dict[str, Any]) -> float:
    min_salary = float(agent.get("min_salary") or 0)
    if min_salary <= 0:
        return 1.0
    job_max = float(job.get("salary_max") or job.get("salary_min") or 0)
    if job_max <= 0:
        return 0.3
    if job_max >= min_salary:
        return 1.0
    ratio = job_max / min_salary
    return max(0.0, ratio - 0.15)


def score_visa(job: Dict[str, Any], agent: Dict[str, Any]) -> float:
    if not agent.get("visa_required"):
        return 1.0
    return 1.0 if job.get("visa_sponsorship") else 0.0


def score_accommodation(job: Dict[str, Any], agent: Dict[str, Any]) -> float:
    if not agent.get("accommodation_required"):
        return 1.0
    return 1.0 if job.get("accommodation") else 0.0


def compute_match_score(job: Dict[str, Any], agent: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
    breakdown = {
        "country": score_country(job, agent) * WEIGHTS["country"],
        "title": score_title(job, agent) * WEIGHTS["title"],
        "salary": score_salary(job, agent) * WEIGHTS["salary"],
        "visa": score_visa(job, agent) * WEIGHTS["visa"],
        "accommodation": score_accommodation(job, agent) * WEIGHTS["accommodation"],
    }
    total = sum(breakdown.values())
    score = round(max(0.0, min(100.0, total)))
    return score, breakdown


def score_label(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "mid"
    return "low"
