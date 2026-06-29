# JSON Database Structure

GulfJobs AI Agent uses flat JSON files instead of a real database, so the whole project can run for free with no backend server. All files live in `/data`. The frontend reads `jobs.json` and `agents.json` directly with `fetch()`. The Python automation in `/scripts` and `/bot` reads and rewrites all four files.

## `data/jobs.json`

A flat array — the master job pool, refreshed by `scripts/scraper.py` on every scheduled run.

```json
[
  {
    "id": "job_0001",
    "title": "Barista",
    "company": "Burj Al Arab Lounge",
    "country": "UAE",
    "city": "Dubai",
    "salary_min": 900,
    "salary_max": 1100,
    "currency": "USD",
    "visa_sponsorship": true,
    "accommodation": false,
    "description": "Raw job description text, used for visa + scam keyword detection.",
    "source": "Bayt | GulfTalent | Naukrigulf | Indeed | Company career page",
    "url": "https://...",
    "posted_date": "YYYY-MM-DD",
    "company_verified": true
  }
]
```

`id` is a deterministic hash of `title + company + country + source` (see `assets/js/dedupe.js` and `scripts/scraper.py`), so the exact same listing always gets the exact same id even if it's re-scraped tomorrow — this is what duplicate detection relies on.

## `data/agents.json`

A flat array of every registered job agent.

```json
[
  {
    "id": "agent_0001",
    "name": "Aïsha Rahman",
    "telegram_username": "aisha_demo",
    "telegram_chat_id": null,
    "countries": ["UAE", "Qatar"],
    "job_titles": ["Barista", "Hospitality"],
    "min_salary": 800,
    "visa_required": true,
    "accommodation_required": false,
    "created_at": "ISO-8601 timestamp",
    "active": true
  }
]
```

- `telegram_chat_id` starts as `null` and is filled in automatically by `bot/telegram_bot.py` the first time that user's Telegram deep link is opened (`/start`) — this is what lets the notifier message the right chat.
- The website saves a copy of this object straight to the visitor's browser `localStorage` (key `gulfjobs_agent`) so the dashboard works instantly, even before the Telegram bot has run.

## `data/sent_log.json`

Prevents the same job from ever being pushed to the same agent twice on Telegram.

```json
{
  "sent": {
    "agent_0001": ["job_0001", "job_0007"]
  }
}
```

## `data/reports.json`

History of daily reports, the same numbers the `/report` Telegram command returns on demand.

```json
{
  "reports": [
    {
      "date": "YYYY-MM-DD",
      "total_jobs_found": 20,
      "high_matches": 6,
      "visa_sponsored_jobs": 14,
      "scam_jobs_flagged": 2,
      "best_opportunity": {
        "id": "job_0001",
        "title": "Barista",
        "company": "Burj Al Arab Lounge",
        "country": "UAE",
        "match_score": 92
      }
    }
  ]
}
```

## Why JSON files instead of a real database?

It keeps the entire MVP free and serverless — GitHub Pages serves the JSON as static files, and GitHub Actions is the only thing that ever writes to them. Each file maps cleanly onto a future Postgres/SQLite table (`jobs`, `agents`, `sent_log`, `reports`) if the project grows beyond the MVP stage.
