"""
scripts/scraper.py
-----------------------------------------------------------------------
Job source aggregator. Combines Google Jobs scraping + Indeed/Bayt
with mock data as fallback.

Requires: pip install requests beautifulsoup4 lxml
-----------------------------------------------------------------------
"""

from __future__ import annotations
import json
import random
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

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

SOURCES = ["Google Jobs", "Indeed", "Bayt", "GulfTalent", "Naukrigulf"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------
# Job ID generation (stable deduplication)
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
# Google Jobs Scraper
# ---------------------------------------------------------------------
def fetch_google_jobs(country: str) -> List[Dict[str, Any]]:
    """Search Google Jobs for Gulf hospitality positions."""
    jobs = []
    search_terms = [
        "hospitality jobs",
        "hotel jobs",
        "barista jobs",
        "waiter jobs",
        "housekeeping jobs",
        "customer service jobs"
    ]
    
    for term in search_terms:
        try:
            query = f"{term} in {country} gulf"
            url = f"https://www.google.com/search?q={quote_plus(query)}&ibp=htl;jobs"
            print(f"  Google Jobs: {query}")
            
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"    -> HTTP {resp.status_code}")
                continue
                
            soup = BeautifulSoup(resp.text, "lxml")
            
            # Google Jobs result cards
            cards = soup.find_all("div", class_=re.compile("BjJfJf|PUpOsf|gws-plugins-horizon-jobs__li-ed"))
            
            if not cards:
                # Try alternative selectors
                cards = soup.find_all("li", class_=re.compile("iFjolb|gws-plugins-horizon-jobs"))
            
            for card in cards[:8]:
                try:
                    title_el = (
                        card.find("div", class_=re.compile("BjJfJf")) or
                        card.find("h2") or
                        card.find("div", role="heading")
                    )
                    company_el = (
                        card.find("div", class_=re.compile("vNEEBe")) or
                        card.find("span", class_=re.compile("company"))
                    )
                    location_el = (
                        card.find("div", class_=re.compile("Qk80Jf")) or
                        card.find("span", class_=re.compile("location"))
                    )
                    
                    if not title_el:
                        continue
                        
                    title = title_el.get_text(strip=True)
                    company = company_el.get_text(strip=True) if company_el else "Unknown"
                    location = location_el.get_text(strip=True) if location_el else country
                    
                    # Clean location
                    location_clean = location.split("·")[0].strip()
                    location_clean = location_clean.split("via")[0].strip()
                    
                    city = country
                    for c in COUNTRY_INFO.get(country, []):
                        if c.lower() in location_clean.lower():
                            city = c
                            break
                    
                    job_data = {
                        "id": "",
                        "title": title,
                        "company": company,
                        "country": country,
                        "city": city,
                        "salary_min": 0,
                        "salary_max": 0,
                        "currency": "USD",
                        "visa_sponsorship": None,
                        "accommodation": None,
                        "description": f"{title} at {company} in {location_clean}",
                        "source": "Google Jobs",
                        "url": url,
                        "posted_date": date.today().isoformat(),
                        "company_verified": True,
                    }
                    job_data["id"] = generate_job_id(job_data)
                    jobs.append(job_data)
                    
                except Exception as e:
                    print(f"    -> Card parse error: {e}")
                    continue
                    
            time.sleep(2)
            
        except Exception as e:
            print(f"  -> Google Jobs error for '{term}': {e}")
            continue
            
    print(f"  -> Google Jobs ({country}): {len(jobs)} found")
    return jobs


# ---------------------------------------------------------------------
# Stubs for other sources
# ---------------------------------------------------------------------
def fetch_indeed(country: str) -> List[Dict[str, Any]]:
    """Indeed blocks scrapers — use Google Jobs above instead."""
    return []


def fetch_bayt(country: str) -> List[Dict[str, Any]]:
    """Bayt blocks scrapers — use Google Jobs above instead."""
    return []


def fetch_gulftalent(country: str) -> List[Dict[str, Any]]:
    return []


def fetch_naukrigulf(country: str) -> List[Dict[str, Any]]:
    return []


SOURCE_FETCHERS = {
    "Google Jobs": fetch_google_jobs,
    "Indeed": fetch_indeed,
    "Bayt": fetch_bayt,
    "GulfTalent": fetch_gulftalent,
    "Naukrigulf": fetch_naukrigulf,
}


# ---------------------------------------------------------------------
# Mock data (fallback)
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
        desc_bits.append("Visa sponsorship and employment visa provided.")
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


def fetch_all_jobs(new_mock_count: int = 2) -> List[Dict[str, Any]]:
    """Combines existing jobs + Google Jobs scraping + mock fallback."""
    existing_jobs = load_existing_jobs()
    existing_ids = {j["id"] for j in existing_jobs}

    # Real scraping
    live_jobs: List[Dict[str, Any]] = []
    for country in COUNTRY_INFO:
        for name, fetcher in SOURCE_FETCHERS.items():
            try:
                results = fetcher(country)
                live_jobs.extend(results)
            except Exception as e:
                print(f"  -> {name} ({country}) failed: {e}")

    # Mock fallback
    next_seq = len(existing_jobs) + len(live_jobs) + 1
    mock_jobs = []
    if not live_jobs:
        print("  No real jobs found — generating mock jobs as fallback")
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
