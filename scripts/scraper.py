"""
scripts/scraper.py
-----------------------------------------------------------------------
Job source aggregator. Combines real job board scraping with mock data
as fallback for development/testing.

Currently implemented:
  - Indeed.ae (real scraping via requests + BeautifulSoup)
  - Mock generator (fallback when scraping fails)

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

SOURCES = ["Indeed", "Bayt", "GulfTalent", "Naukrigulf", "Company career page"]

# User-Agent to avoid being blocked
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------
# Helper: hash-based job IDs (stable deduplication)
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
# Indeed.ae Scraper (REAL JOBS)
# ---------------------------------------------------------------------

def fetch_indeed(country: str) -> List[Dict[str, Any]]:
    """Search Google Jobs for Gulf hospitality positions."""
    jobs = []
    search_terms = ["hospitality jobs", "hotel jobs", "barista", "waiter", "housekeeping"]
    
    for term in search_terms:
        try:
            query = f"{term} {country} gulf jobs"
            url = f"https://www.google.com/search?q={quote_plus(query)}&ibp=htl;jobs"
            print(f"  Searching: {query}")
            
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
                
            soup = BeautifulSoup(resp.text, "lxml")
            # Google Jobs cards
            cards = soup.find_all("div", class_=re.compile("BjJfJf|PUpOsf"))
            
            for card in cards[:10]:
                try:
                    title_el = card.find("div", class_=re.compile("BjJfJf"))
                    company_el = card.find("div", class_=re.compile("vNEEBe"))
                    location_el = card.find("div", class_=re.compile("Qk80Jf"))
                    
                    if not title_el:
                        continue
                        
                    title = title_el.get_text(strip=True)
                    company = company_el.get_text(strip=True) if company_el else "Unknown"
                    location = location_el.get_text(strip=True) if location_el else country
                    
                    city = country
                    for c in COUNTRY_INFO.get(country, []):
                        if c.lower() in location.lower():
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
                        "description": f"{title} at {company} in {location}",
                        "source": "Google Jobs",
                        "url": url,
                        "posted_date": date.today().isoformat(),
                        "company_verified": True,
                    }
                    job_data["id"] = generate_job_id(job_data)
                    jobs.append(job_data)
                    
                except Exception:
                    continue
                    
            time.sleep(3)
            
        except Exception as e:
            print(f"  -> Error: {e}")
            
    print(f"  -> Google Jobs ({country}): {len(jobs)} jobs found")
    return jobs

# ---------------------------------------------------------------------
# Bayt.com Scraper (REAL JOBS)
# ---------------------------------------------------------------------
def fetch_bayt(country: str) -> List[Dict[str, Any]]:
    """Scrapes Bayt.com for Gulf hospitality jobs."""
    jobs = []
    try:
        # Bayt search URL format
        url = f"https://www.bayt.com/en/{country.lower().replace(' ', '-')}/jobs/?sort=date"
        print(f"  Scraping Bayt: {url}")
        
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"    -> HTTP {resp.status_code}, skipping")
            return jobs

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.find_all("li", class_=re.compile("has-pointer-d|jb-list-item"))
        
        for card in cards[:10]:
            try:
                title_el = card.find("h2") or card.find("a", class_=re.compile("jb-title"))
                company_el = card.find("b") or card.find("div", class_=re.compile("jb-company"))
                location_el = card.find("dd") or card.find("span", class_=re.compile("jb-location"))
                link_el = card.find("a", href=re.compile("/en/"))

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                location_text = location_el.get_text(strip=True) if location_el else country
                
                city = country
                for c in COUNTRY_INFO.get(country, []):
                    if c.lower() in location_text.lower():
                        city = c
                        break

                url_link = ""
                if link_el:
                    href = link_el.get("href", "")
                    if href.startswith("/"):
                        url_link = f"https://www.bayt.com{href}"
                    else:
                        url_link = href

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
                    "description": title,
                    "source": "Bayt",
                    "url": url_link,
                    "posted_date": date.today().isoformat(),
                    "company_verified": True,
                }
                job_data["id"] = generate_job_id(job_data)
                jobs.append(job_data)

            except Exception as e:
                print(f"    -> Error parsing Bayt card: {e}")
                continue

        time.sleep(2)

    except Exception as e:
        print(f"  -> Bayt error for {country}: {e}")

    print(f"  -> Bayt ({country}): {len(jobs)} jobs found")
    return jobs


# ---------------------------------------------------------------------
# Stubs for other sources (ready for future implementation)
# ---------------------------------------------------------------------
def fetch_gulftalent(country: str) -> List[Dict[str, Any]]:
    """TODO: GulfTalent requires API key or advanced scraping."""
    return []


def fetch_naukrigulf(country: str) -> List[Dict[str, Any]]:
    """TODO: NaukriGulf blocks scrapers — needs API."""
    return []


def fetch_company_career_pages(country: str) -> List[Dict[str, Any]]:
    """TODO: Add direct career page scrapers for major Gulf hotels."""
    return []


SOURCE_FETCHERS = {
    "Indeed": fetch_indeed,
    "Bayt": fetch_bayt,
    "GulfTalent": fetch_gulftalent,
    "Naukrigulf": fetch_naukrigulf,
    "Company career page": fetch_company_career_pages,
}


# ---------------------------------------------------------------------
# Mock data (fallback when scrapers return nothing)
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
        ]))
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


def fetch_all_jobs(new_mock_count: int = 3) -> List[Dict[str, Any]]:
    """Combines existing jobs + real scraping + mock fallback."""
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

    # Mock fallback only if no real jobs found
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
