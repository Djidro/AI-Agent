"""
scripts/scraper.py
-----------------------------------------------------------------------
Job source aggregator. For this MVP, real scraping is replaced with a
clean mock generator so the whole pipeline (dedupe -> scam/visa
detection -> match scoring -> Telegram notification) is fully working
end to end without needing any paid APIs or fragile scrapers.

Each fetch_* function below is the integration point for a real source.
They currently return [] — implement one to go live with that source.
Whatever they return must match the job schema documented in
data/schema.md (same fields as the bundled data/jobs.json).

Run directly to refresh data/jobs.json:
    python scripts/scraper.py
-----------------------------------------------------------------------
"""

from __future__ import annotations
import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
JOBS_FILE = ROOT / "data" / "jobs.json"

TITLES = ["Barista", "Waiter", "Hotel Front Desk Agent", "Housekeeping Staff", "Customer Service Representative"]

COUNTRY_INFO = {
    "UAE": ["Dubai", "Abu Dhabi", "Sharjah"],
    "Qatar": ["Doha", "Al Wakrah"],
    "Oman": ["Muscat", "Salalah"],
    "Saudi Arabia": ["Riyadh", "Jeddah", "Dammam"],
    "Kuwait": ["Kuwait City"],
    "Bahrain": ["Manama"],
}

COMPANIES = [
    "Burj Al Arab Lounge", "Pearl Resort & Spa", "Marina Grill House", "Costa Coffee Gulf",
    "Shangri-La Hospitality Group", "Riyadh Grand Hotel", "Ooredoo Customer Care",
    "Manama Bay Resort", "Jeddah Heights Hotel", "Salalah Garden Resort",
]

SOURCES = ["Indeed", "Bayt", "GulfTalent", "Naukrigulf", "Company career page"]


# ---------------------------------------------------------------------
# Real source integration points — implement to go live, currently stubs
# ---------------------------------------------------------------------
def fetch_indeed(country: str) -> List[Dict[str, Any]]:
    """TODO: implement a real Indeed integration. Returns [] until then."""
    return []


def fetch_bayt(country: str) -> List[Dict[str, Any]]:
    """TODO: implement a real Bayt integration. Returns [] until then."""
    return []


def fetch_gulftalent(country: str) -> List[Dict[str, Any]]:
    """TODO: implement a real GulfTalent integration. Returns [] until then."""
    return []


def fetch_naukrigulf(country: str) -> List[Dict[str, Any]]:
    """TODO: implement a real Naukrigulf integration. Returns [] until then."""
    return []


def fetch_company_career_pages(country: str) -> List[Dict[str, Any]]:
    """TODO: implement direct company career-page scrapers. Returns [] until then."""
    return []


SOURCE_FETCHERS = {
    "Indeed": fetch_indeed,
    "Bayt": fetch_bayt,
    "GulfTalent": fetch_gulftalent,
    "Naukrigulf": fetch_naukrigulf,
    "Company career page": fetch_company_career_pages,
}


# ---------------------------------------------------------------------
# Deterministic id generation — mirrors assets/js/dedupe.js so ids stay
# stable for the same listing (title + company + country + source).
# ---------------------------------------------------------------------
def _job_signature(job: Dict[str, Any]) -> str:
    parts = [job.get("title"), job.get("company"), job.get("country"), job.get("source")]
    return "|".join((p or "").strip().lower() for p in parts)


def _hash_string(s: str) -> str:
    h = 5381
    for ch in s:
        h = (h * 33) ^ ord(ch)
        h &= 0xFFFFFFFF  # keep within 32-bit unsigned range, mirrors JS >>> 0
    return format(h, "x")


def generate_job_id(job: Dict[str, Any]) -> str:
    return f"job_{_hash_string(_job_signature(job))}"


def dedupe_jobs(jobs: List[Dict[str, Any]], existing_ids: set) -> List[Dict[str, Any]]:
    seen = set(existing_ids)
    result = []
    for job in jobs:
        job_id = job.get("id") or generate_job_id(job)
        if job_id in seen:
            continue
        seen.add(job_id)
        job = dict(job)
        job["id"] = job_id
        result.append(job)
    return result


# ---------------------------------------------------------------------
# Mock data generation (MVP placeholder for live scraping)
# ---------------------------------------------------------------------
def _generate_mock_job(next_seq: int) -> Dict[str, Any]:
    title = random.choice(TITLES)
    country = random.choice(list(COUNTRY_INFO.keys()))
    city = random.choice(COUNTRY_INFO[country])
    company = random.choice(COMPANIES)
    source = random.choice(SOURCES)
    visa = random.random() > 0.2
    accommodation = random.random() > 0.45
    salary_min = random.randint(550, 1100)
    salary_max = salary_min + random.randint(80, 250)

    desc_bits = [f"{title} position open at {company} in {city}, {country}."]
    if visa:
        desc_bits.append(random.choice([
            "Visa sponsorship and employment visa provided.",
            "Work permit fully sponsored by employer.",
            "Relocation assistance included for the right candidate.",
        ]))
    if accommodation:
        desc_bits.append("Staff accommodation provided.")
    desc_bits.append("Apply with an updated CV and recent photo.")

    return {
        "id": f"job_{next_seq:04d}",
        "title": title,
        "company": company,
        "country": country,
        "city": city,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": "USD",
        "visa_sponsorship": visa,
        "accommodation": accommodation,
        "description": " ".join(desc_bits),
        "source": source,
        "url": f"https://example-careers.com/jobs/{title.lower().replace(' ', '-')}-{next_seq:04d}",
        "posted_date": (date.today() - timedelta(days=random.randint(0, 5))).isoformat(),
        "company_verified": True,
    }


def load_existing_jobs() -> List[Dict[str, Any]]:
    if not JOBS_FILE.exists():
        return []
    with open(JOBS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_all_jobs(new_mock_count: int = 3) -> List[Dict[str, Any]]:
    """
    Combines existing jobs already on disk with any live-source results
    (currently empty stubs, ready for real integrations) and a handful of
    freshly generated mock jobs, then runs everything through duplicate
    detection so ids never collide.
    """
    existing_jobs = load_existing_jobs()
    existing_ids = {j["id"] for j in existing_jobs}

    live_jobs: List[Dict[str, Any]] = []
    for country in COUNTRY_INFO:
        for fetcher in SOURCE_FETCHERS.values():
            live_jobs.extend(fetcher(country))

    next_seq = len(existing_jobs) + 1
    mock_jobs = [_generate_mock_job(next_seq + i) for i in range(new_mock_count)]

    combined = existing_jobs + live_jobs + mock_jobs
    return dedupe_jobs(combined, existing_ids=set())


def save_jobs(jobs: List[Dict[str, Any]]) -> None:
    JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    jobs = fetch_all_jobs()
    save_jobs(jobs)
    print(f"Saved {len(jobs)} jobs to {JOBS_FILE}")
