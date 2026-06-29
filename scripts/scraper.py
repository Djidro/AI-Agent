"""
scripts/scraper.py
-----------------------------------------------------------------------
Job source aggregator using Adzuna API for real Gulf hospitality jobs.
Falls back to mock data only when API is unavailable.

Requires: pip install requests python-dotenv
-----------------------------------------------------------------------
"""

from __future__ import annotations
import json
import os
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
JOBS_FILE = ROOT / "data" / "jobs.json"

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

# Adzuna country codes
COUNTRY_CODES = {
    "UAE": "ae",
    "Qatar": "qa",
    "Saudi Arabia": "sa",
    "Kuwait": "kw",
    "Bahrain": "bh",
    "Oman": "om",
}

COUNTRY_INFO = {
    "UAE": ["Dubai", "Abu Dhabi", "Sharjah"],
    "Qatar": ["Doha", "Al Wakrah"],
    "Oman": ["Muscat", "Salalah"],
    "Saudi Arabia": ["Riyadh", "Jeddah", "Dammam"],
    "Kuwait": ["Kuwait City"],
    "Bahrain": ["Manama"],
}

COMPANIES = [
    "Burj Al Arab Lounge", "Pearl Resort & Spa", "Marina Grill House",
    "Shangri-La Hospitality Group", "Riyadh Grand Hotel", "Manama Bay Resort",
]

TITLES = ["Barista", "Waiter", "Hotel Staff", "Housekeeping", "Customer Service"]

HEADERS = {"User-Agent": "GulfJobs-AI-Agent/1.0"}


# ---------------------------------------------------------------------
# Job ID helpers
# ---------------------------------------------------------------------
def _job_signature(job: Dict[str, Any]) -> str:
    parts = [job.get("title"), job.get("company"), job.get("country"), job.get("source")]
    return "|".join((p or "").strip().lower() for p in parts)


def _hash_string(s: str) -> str:
    h = 5381
    for ch in s:
        h = (h * 33) ^ ord(ch)
        h &= 0xFFFFFFFF
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
# Adzuna API (REAL JOBS)
# ---------------------------------------------------------------------
def fetch_adzuna(country: str) -> List[Dict[str, Any]]:
    """Fetch real hospitality jobs from Adzuna API."""
    jobs = []
    country_code = COUNTRY_CODES.get(country)
    if not country_code or not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return jobs

    # Search terms for hospitality
    queries = ["hospitality", "hotel", "barista", "waiter", "housekeeping", "customer service"]

    for query in queries:
        try:
            url = (
                f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
                f"?app_id={ADZUNA_APP_ID}"
                f"&app_key={ADZUNA_APP_KEY}"
                f"&what={query}"
                f"&results_per_page=10"
                f"&content-type=application/json"
            )
            print(f"  Adzuna ({country}): {query}")
            resp = requests.get(url, headers=HEADERS, timeout=15)

            if resp.status_code != 200:
                print(f"    -> HTTP {resp.status_code}")
                continue

            data = resp.json()
            results = data.get("results", [])

            for item in results:
                try:
                    title = item.get("title", "")
                    company = item.get("company", {}).get("display_name", "Unknown")
                    location = item.get("location", {}).get("display_name", country)
                    description = item.get("description", "")[:300]
                    redirect_url = item.get("redirect_url", "")
                    salary_min = int(item.get("salary_min", 0) or 0)
                    salary_max = int(item.get("salary_max", 0) or 0)
                    created = item.get("created", date.today().isoformat())

                    # Extract city
                    city = country
                    for c in COUNTRY_INFO.get(country, []):
                        if c.lower() in location.lower():
                            city = c
                            break

                    # Check for visa sponsorship in description
                    visa = None
                    desc_lower = description.lower()
                    if any(w in desc_lower for w in ["visa sponsorship", "visa provided", "work permit", "employment visa"]):
                        visa = True

                    # Check for accommodation
                    accommodation = None
                    if any(w in desc_lower for w in ["accommodation", "housing", "stay", "lodging"]):
                        accommodation = True

                    job_data = {
                        "id": "",
                        "title": title,
                        "company": company,
                        "country": country,
                        "city": city,
                        "salary_min": salary_min,
                        "salary_max": salary_max,
                        "currency": "USD",
                        "visa_sponsorship": visa,
                        "accommodation": accommodation,
                        "description": description,
                        "source": "Adzuna",
                        "url": redirect_url,
                        "posted_date": created,
                        "company_verified": True,
                    }
                    job_data["id"] = generate_job_id(job_data)
                    jobs.append(job_data)

                except Exception as e:
                    print(f"    -> Parse error: {e}")
                    continue

            time.sleep(1)  # Rate limit: 1 request per second

        except Exception as e:
            print(f"  -> Error: {e}")
            continue

    print(f"  -> Adzuna ({country}): {len(jobs)} jobs found")
    return jobs


# ---------------------------------------------------------------------
# Mock fallback
# ---------------------------------------------------------------------
def _generate_mock_job(next_seq: int) -> Dict[str, Any]:
    title = random.choice(TITLES)
    country = random.choice(list(COUNTRY_INFO.keys()))
    city = random.choice(COUNTRY_INFO[country])
    company = random.choice(COMPANIES)
    visa = random.random() > 0.2
    accommodation = random.random() > 0.45
    salary_min = random.randint(550, 1100)
    salary_max = salary_min + random.randint(80, 250)

    desc_bits = [f"{title} at {company} in {city}, {country}."]
    if visa:
        desc_bits.append("Visa sponsorship provided.")
    if accommodation:
        desc_bits.append("Staff accommodation provided.")

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
        "source": "Adzuna",
        "url": f"https://example-careers.com/jobs/{title.lower().replace(' ', '-')}-{next_seq:04d}",
        "posted_date": (date.today() - timedelta(days=random.randint(0, 5))).isoformat(),
        "company_verified": True,
    }


def load_existing_jobs() -> List[Dict[str, Any]]:
    if not JOBS_FILE.exists():
        return []
    with open(JOBS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_all_jobs(new_mock_count: int = 0) -> List[Dict[str, Any]]:
    """Fetch real jobs from Adzuna API. No mock fallback."""
    existing_jobs = load_existing_jobs()
    existing_ids = {j["id"] for j in existing_jobs}

    live_jobs: List[Dict[str, Any]] = []
    for country in COUNTRY_CODES:
        try:
            results = fetch_adzuna(country)
            live_jobs.extend(results)
        except Exception as e:
            print(f"  -> Adzuna ({country}) failed: {e}")

    combined = existing_jobs + live_jobs
    return dedupe_jobs(combined, existing_ids=set())


def save_jobs(jobs: List[Dict[str, Any]]) -> None:
    JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    print("Fetching real jobs from Adzuna API...")
    jobs = fetch_all_jobs()
    save_jobs(jobs)
    print(f"\nSaved {len(jobs)} jobs to {JOBS_FILE}")
