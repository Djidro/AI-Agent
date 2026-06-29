# GulfJobs AI Agent

An AI-powered job hunting agent for hospitality and customer service roles across the Gulf — UAE, Qatar, Oman, Saudi Arabia, Kuwait, and Bahrain. Set up a personal job agent once; it keeps scoring new jobs against your profile and pushes only the best matches to Telegram, even while you're offline.

100% free to run: static frontend on **GitHub Pages**, automation on **GitHub Actions**, notifications via a **Telegram Bot**, **JSON files** as the database. No backend server, no paid services.

---

## Folder structure

```
gulfjobs-ai-agent/
├── index.html                      # Landing page ("Night Shift Radar" design)
├── create-agent.html               # 3-step job agent creation form
├── dashboard.html                  # Sidebar dashboard: overview/matches/saved/reports/settings
├── README.md
├── assets/
│   ├── css/
│   │   └── styles.css              # Full design system + responsive layout
│   └── js/
│       ├── app.js                  # Landing page behaviour (smooth scroll, live job count)
│       ├── create-agent.js         # 3-step form logic + Telegram deep-link builder
│       ├── dashboard.js            # Dashboard data pipeline + rendering
│       ├── matchEngine.js          # AI Match Score (client-side)
│       ├── scamDetector.js         # Visa detection + scam heuristics (client-side)
│       └── dedupe.js               # Duplicate detection (client-side)
├── data/
│   ├── jobs.json                   # Sample job dataset (flat array, master pool)
│   ├── agents.json                 # Registered job agents (used by bot + automation)
│   ├── sent_log.json               # Server-side duplicate-notification log
│   ├── reports.json                # Daily report history
│   └── schema.md                   # Full JSON schema documentation
├── scripts/
│   ├── scraper.py                  # Job source aggregator (mock data + scraper hooks)
│   ├── match_engine.py             # Python port of matchEngine.js (server-side)
│   └── scam_detector.py            # Python port of scamDetector.js (server-side)
├── bot/
│   ├── telegram_bot.py             # Interactive bot: /start /jobs /matches /report /visa /help
│   ├── notifier.py                 # Scheduled push run by GitHub Actions
│   └── requirements.txt
├── docs/
│   └── TELEGRAM_BOT_GUIDE.md       # Full Telegram bot setup walkthrough
└── .github/
    └── workflows/
        └── daily-job-search.yml    # Scheduled automation (every 6 hours)
```

---

## Core features

- **AI Match Score (0–100)** — weighted on country (25), job title (30), salary (20), visa sponsorship (15), accommodation (10). The exact same logic lives in `assets/js/matchEngine.js` (frontend) and `scripts/match_engine.py` (backend) so scores always agree everywhere.
- **Visa Sponsorship Detection** — scans descriptions for phrases like "visa sponsorship", "employment visa", "work permit", "relocation assistance".
- **Duplicate Detection** — every job gets a deterministic id derived from `title + company + country + source` (`assets/js/dedupe.js` / `scripts/scraper.py`), so the same listing is never shown or sent twice, even if re-scraped.
- **Scam Detection** — flags missing/invalid company names, unrealistic salaries, suspicious shortened links, insecure (non-HTTPS) links, and common scam phrasing.
- **Telegram Bot** — `/start`, `/jobs`, `/matches`, `/report`, `/visa`, `/help`, plus automatic push alerts for new high-match jobs (score 70+) and an on-demand daily report.
- **Dashboard** — sidebar layout with overview stats, latest opportunities (filterable, ranked by score), saved jobs, a daily report panel, and agent settings.
- **Telegram deep-link onboarding** — the create-agent form encodes your preferences directly into a `t.me/...?start=...` link so finishing setup on the website instantly activates the bot, with a conversational fallback if the payload would be too long for Telegram's start-parameter limit.

---

## How the automation works (no backend server)

1. **GitHub Actions** runs `.github/workflows/daily-job-search.yml` on a schedule (every 6 hours, configurable via the cron expression).
2. It executes `bot/notifier.py`, which:
   - Refreshes `data/jobs.json` via `scripts/scraper.py` (mock data for the MVP; real scraper hooks are already stubbed in for Indeed, Bayt, GulfTalent, Naukrigulf, and company career pages).
   - Loads every agent from `data/agents.json`.
   - Scores every job for every agent with `scripts/match_engine.py`, flags scams with `scripts/scam_detector.py`.
   - Sends a Telegram message for every **new** high-match (70+) job using each agent's stored `telegram_chat_id`.
   - Updates `data/sent_log.json` so nothing is ever sent twice.
   - Appends a summary to `data/reports.json`.
3. The workflow commits the updated JSON files back to the repo, so `dashboard.html` (served by GitHub Pages) reflects fresh data on next load.
4. For **inbound** Telegram commands (`/jobs`, `/matches`, etc.) and `/start` registration, run `bot/telegram_bot.py` on any free always-on host — GitHub Actions itself can't keep a process listening 24/7. Full instructions: [`docs/TELEGRAM_BOT_GUIDE.md`](docs/TELEGRAM_BOT_GUIDE.md).

---

## Getting started

### 1. Deploy the website to GitHub Pages

1. Push this entire project to a new GitHub repository.
2. **Settings → Pages → Build and deployment → Source: Deploy from a branch.**
3. Branch: `main`, folder: `/ (root)`. Save.
4. Your site goes live at `https://<your-username>.github.io/<your-repo-name>/`.
5. Visit `index.html` → create a job agent → view the dashboard. It works immediately with the bundled sample dataset — no setup required for the static demo.

### 2. Set up the Telegram bot

Follow [`docs/TELEGRAM_BOT_GUIDE.md`](docs/TELEGRAM_BOT_GUIDE.md):
- Create a bot with @BotFather, update `BOT_USERNAME` in `assets/js/create-agent.js`
- Add the `TELEGRAM_BOT_TOKEN` GitHub secret (for scheduled alerts)
- Run `bot/telegram_bot.py` somewhere always-on (for /start registration and instant command replies)

### 3. Enable the scheduled automation

Once the `TELEGRAM_BOT_TOKEN` secret is set, `.github/workflows/daily-job-search.yml` runs automatically on its cron schedule. You can also trigger it manually from the **Actions** tab (**Run workflow** — it's set up with `workflow_dispatch`).

---

## Local development

No build step or bundler — it's plain HTML/CSS/JS.

```bash
python -m http.server 8000
# open http://localhost:8000
```

Test the Python automation locally:

```bash
cd bot
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your-token-here"   # optional, omit for a dry run that just prints
python notifier.py
```

Run the interactive bot locally:

```bash
cd bot
python telegram_bot.py
```

---

## Adding a real job source later

`scripts/scraper.py` already defines the integration points:

```python
def fetch_indeed(country: str) -> List[Dict[str, Any]]: ...
def fetch_bayt(country: str) -> List[Dict[str, Any]]: ...
def fetch_gulftalent(country: str) -> List[Dict[str, Any]]: ...
def fetch_naukrigulf(country: str) -> List[Dict[str, Any]]: ...
def fetch_company_career_pages(country: str) -> List[Dict[str, Any]]: ...
```

Each currently returns `[]`. Implement any of them (scraper, RSS feed, or official API) to return job dicts matching the schema in [`data/schema.md`](data/schema.md), and the rest of the pipeline — duplicate detection, scam/visa detection, matching, Telegram alerts, dashboard rendering — works unchanged.

---

## Tech stack

| Layer          | Technology                          |
|----------------|--------------------------------------|
| Frontend       | HTML5, CSS3, Vanilla JavaScript      |
| Hosting        | GitHub Pages (free, static)          |
| Automation     | GitHub Actions (scheduled workflow)  |
| Notifications  | Telegram Bot API                     |
| Storage        | JSON files (`/data`)                 |
| Backend logic  | Python 3.11 (`/scripts`, `/bot`)     |

---

## Roadmap (post-MVP)

- Replace JSON files with a real database (Postgres/SQLite) — schema already maps 1:1, see `data/schema.md`
- Implement live scrapers for Indeed, Bayt, GulfTalent, Naukrigulf, and company career pages
- Multi-agent support per user
- Email digest as a Telegram alternative
- Admin panel for reviewing flagged scam listings
- Paid tier with sub-hourly scanning

---

## License

This MVP is provided as a starting point for your own SaaS build. Adapt freely.
