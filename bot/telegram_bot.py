"""
bot/telegram_bot.py
-----------------------------------------------------------------------
Interactive Telegram bot for GulfJobs AI Agent.

Commands:
  /start    - register this Telegram chat (via deep link from
              create-agent.html, or conversationally if no payload)
  /jobs     - show the 5 most recently posted jobs
  /matches  - show this agent's best matches (score 45+, sorted)
  /report   - generate an on-demand daily report
  /visa     - show visa-sponsored jobs only
  /help     - list all commands

HOSTING NOTE:
GitHub Actions (.github/workflows/daily-job-search.yml) runs on a
SCHEDULE — it is not designed to keep a process alive 24/7 listening
for incoming messages. That workflow instead runs bot/notifier.py,
which only sends OUTBOUND alerts.

This script needs a persistent process for INBOUND commands. Run it
locally, or on any free always-on host (Railway / Render / Fly.io /
your own machine). Full instructions: docs/TELEGRAM_BOT_GUIDE.md

Dependencies: requests only (see requirements.txt).
-----------------------------------------------------------------------
"""

from __future__ import annotations
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

sys.path.append(str(Path(__file__).resolve().parent.parent / "scripts"))
from match_engine import compute_match_score, score_label  # noqa: E402
from scam_detector import detect_visa_sponsorship, detect_scam  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
AGENTS_FILE = DATA_DIR / "agents.json"
JOBS_FILE = DATA_DIR / "jobs.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
POLL_TIMEOUT = 25

# Must match COUNTRY_CODES / TITLE_CODES in assets/js/create-agent.js exactly.
COUNTRY_CODES = {"UAE": "UAE", "QAT": "Qatar", "OMN": "Oman", "SAU": "Saudi Arabia", "KWT": "Kuwait", "BHR": "Bahrain"}
TITLE_CODES = {"BAR": "Barista", "WAI": "Waiter", "HOT": "Hotel Staff", "HSP": "Hospitality", "CUS": "Customer Service"}

HELP_TEXT = (
    "🤖 *GulfJobs AI Agent — Commands*\n\n"
    "/start — activate your agent and link this chat\n"
    "/jobs — latest job opportunities\n"
    "/matches — your best matches (45+ score)\n"
    "/report — today's summary report\n"
    "/visa — visa-sponsored jobs only\n"
    "/help — show this list again"
)

# In-memory state for the conversational onboarding fallback
# (used when the deep-link payload is missing/too long).
_pending_setup: Dict[int, Dict[str, Any]] = {}


# ---------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------
def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_jobs() -> List[Dict[str, Any]]:
    return load_json(JOBS_FILE, [])


def load_agents() -> List[Dict[str, Any]]:
    return load_json(AGENTS_FILE, [])


def save_agents(agents: List[Dict[str, Any]]) -> None:
    save_json(AGENTS_FILE, agents)


def next_agent_id(agents: List[Dict[str, Any]]) -> str:
    return f"agent_{len(agents) + 1:04d}"


def find_agent_by_chat_id(chat_id: int) -> Optional[Dict[str, Any]]:
    return next((a for a in load_agents() if a.get("telegram_chat_id") == chat_id), None)


def find_agent_by_username(username: str) -> Optional[Dict[str, Any]]:
    clean = (username or "").lstrip("@").lower()
    if not clean:
        return None
    return next((a for a in load_agents() if (a.get("telegram_username") or "").lstrip("@").lower() == clean), None)


# ---------------------------------------------------------------------
# Telegram send
# ---------------------------------------------------------------------
def send_message(chat_id: int, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        print(f"[DRY RUN] -> {chat_id}:\n{text}\n")
        return
    try:
        requests.post(
            f"{API_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"Telegram send failed: {e}")


# ---------------------------------------------------------------------
# Deep-link payload decoding
# raw format: v1|C:UAE,QAT|J:BAR,HSP|S:800|VS:1|AC:0
# ---------------------------------------------------------------------
def decode_deep_link(payload: str) -> Optional[Dict[str, Any]]:
    try:
        padded = payload.replace("-", "+").replace("_", "/")
        padded += "=" * (-len(padded) % 4)
        raw = base64.b64decode(padded).decode("utf-8")
    except Exception:
        return None

    if not raw.startswith("v1|"):
        return None

    fields = {}
    for part in raw.split("|")[1:]:
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        fields[key] = value

    countries = [COUNTRY_CODES[c] for c in fields.get("C", "").split(",") if c in COUNTRY_CODES]
    titles = [TITLE_CODES[t] for t in fields.get("J", "").split(",") if t in TITLE_CODES]

    return {
        "countries": countries,
        "job_titles": titles,
        "min_salary": int(fields.get("S", "0") or 0),
        "visa_required": fields.get("VS") == "1",
        "accommodation_required": fields.get("AC") == "1",
    }


# ---------------------------------------------------------------------
# Job formatting
# ---------------------------------------------------------------------
def enrich_job(job: Dict[str, Any], agent: Dict[str, Any]) -> Dict[str, Any]:
    visa_info = detect_visa_sponsorship(job)
    scam_info = detect_scam(job)
    score, _ = compute_match_score(job, agent)
    enriched = dict(job)
    enriched["visa_sponsorship"] = job.get("visa_sponsorship") or visa_info["detected"]
    enriched["scam_flagged"] = scam_info["isSuspicious"]
    enriched["match_score"] = score
    enriched["match_label"] = score_label(score)
    return enriched


def format_job_line(job: Dict[str, Any]) -> str:
    visa = "✅" if job.get("visa_sponsorship") else "❌"
    return (
        f"*{job['title']}* — {job['company']} ({job.get('city', '')}, {job['country']})\n"
        f"Score: {job['match_score']}/100 | Visa: {visa} | ${job.get('salary_min', '?')}–{job.get('salary_max', '?')}/mo\n"
        f"{job.get('url', '')}"
    )


# ---------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------
def handle_jobs(chat_id: int, agent: Dict[str, Any]) -> None:
    enriched = [enrich_job(j, agent) for j in load_jobs()]
    enriched = [j for j in enriched if not j["scam_flagged"]]
    enriched.sort(key=lambda j: j.get("posted_date", ""), reverse=True)
    top = enriched[:5]
    if not top:
        send_message(chat_id, "No jobs found right now. Check back soon!")
        return
    send_message(chat_id, "🆕 *Latest opportunities*\n\n" + "\n\n".join(format_job_line(j) for j in top))


def handle_matches(chat_id: int, agent: Dict[str, Any]) -> None:
    enriched = [enrich_job(j, agent) for j in load_jobs()]
    enriched = [j for j in enriched if not j["scam_flagged"] and j["match_score"] >= 45]
    enriched.sort(key=lambda j: -j["match_score"])
    top = enriched[:5]
    if not top:
        send_message(chat_id, "No strong matches right now. I'll notify you the moment one appears!")
        return
    send_message(chat_id, "🎯 *Your best matches*\n\n" + "\n\n".join(format_job_line(j) for j in top))


def save_report(total: int, high: int, visa: int, scam: int, best: Optional[Dict[str, Any]]) -> None:
    from datetime import date
    payload = load_json(DATA_DIR / "reports.json", {"reports": []})
    payload.setdefault("reports", [])
    payload["reports"].append({
        "date": date.today().isoformat(),
        "total_jobs_found": total,
        "high_matches": high,
        "visa_sponsored_jobs": visa,
        "scam_jobs_flagged": scam,
        "best_opportunity": None if not best else {
            "id": best["id"], "title": best["title"], "company": best["company"],
            "country": best["country"], "match_score": best["match_score"],
        },
    })
    save_json(DATA_DIR / "reports.json", payload)


def handle_report(chat_id: int, agent: Dict[str, Any]) -> None:
    enriched = [enrich_job(j, agent) for j in load_jobs()]
    total = len(enriched)
    high = sum(1 for j in enriched if j["match_label"] == "high" and not j["scam_flagged"])
    visa = sum(1 for j in enriched if j["visa_sponsorship"] and not j["scam_flagged"])
    scam = sum(1 for j in enriched if j["scam_flagged"])
    best = max((j for j in enriched if not j["scam_flagged"]), key=lambda j: j["match_score"], default=None)
    best_line = "No matches yet." if not best else f"{best['title']} — {best['company']} ({best['match_score']}/100)"

    save_report(total, high, visa, scam, best)

    send_message(
        chat_id,
        "📊 *Daily Report*\n\n"
        f"Total jobs found: {total}\n"
        f"High matches: {high}\n"
        f"Visa-sponsored jobs: {visa}\n"
        f"Scam jobs flagged: {scam}\n\n"
        f"🏆 Best opportunity: {best_line}",
    )


def handle_visa(chat_id: int, agent: Dict[str, Any]) -> None:
    enriched = [enrich_job(j, agent) for j in load_jobs()]
    enriched = [j for j in enriched if j["visa_sponsorship"] and not j["scam_flagged"]]
    enriched.sort(key=lambda j: -j["match_score"])
    top = enriched[:5]
    if not top:
        send_message(chat_id, "No visa-sponsored jobs found right now.")
        return
    send_message(chat_id, "🛂 *Visa-sponsored jobs*\n\n" + "\n\n".join(format_job_line(j) for j in top))


# ---------------------------------------------------------------------
# /start — deep link registration, or conversational fallback
# ---------------------------------------------------------------------
def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def handle_start(chat_id: int, username: str, payload: str) -> None:
    decoded = decode_deep_link(payload) if payload and payload != "setup" else None

    if decoded:
        agents = load_agents()
        existing = find_agent_by_username(username)
        if existing:
            existing.update(decoded)
            existing["telegram_chat_id"] = chat_id
            existing["telegram_username"] = username
        else:
            agents.append({
                "id": next_agent_id(agents),
                "name": username or "Job seeker",
                "telegram_username": username,
                "telegram_chat_id": chat_id,
                **decoded,
                "created_at": _now_iso(),
                "active": True,
            })
        save_agents(agents)
        send_message(
            chat_id,
            "✅ You're connected! I'll message you here whenever I find a job matching "
            f"{', '.join(decoded['job_titles']) or 'your roles'} in {', '.join(decoded['countries']) or 'your countries'}.\n\n"
            + HELP_TEXT,
        )
        return

    # No usable payload -> short conversational onboarding
    _pending_setup[chat_id] = {"step": "name", "username": username}
    send_message(
        chat_id,
        "👋 Welcome to *GulfJobs AI Agent*!\n\n"
        "Let's set up your agent here directly. What's your name?",
    )


def continue_onboarding(chat_id: int, text: str) -> bool:
    """Returns True if this message was consumed by the onboarding flow."""
    state = _pending_setup.get(chat_id)
    if not state:
        return False

    step = state["step"]

    if step == "name":
        state["name"] = text.strip()
        state["step"] = "countries"
        send_message(chat_id, "Which countries? (comma-separated, e.g. UAE, Qatar, Oman, Saudi Arabia, Kuwait, Bahrain)")
        return True

    if step == "countries":
        state["countries"] = [c.strip().title() for c in text.split(",") if c.strip()]
        state["step"] = "titles"
        send_message(chat_id, "Which job titles? (comma-separated, e.g. Barista, Waiter, Hotel Staff, Hospitality, Customer Service)")
        return True

    if step == "titles":
        state["job_titles"] = [t.strip().title() for t in text.split(",") if t.strip()]
        state["step"] = "salary"
        send_message(chat_id, "What's your minimum monthly salary in USD? (enter 0 for no minimum)")
        return True

    if step == "salary":
        try:
            state["min_salary"] = int(text.strip())
        except ValueError:
            state["min_salary"] = 0
        state["step"] = "visa"
        send_message(chat_id, "Do you require visa sponsorship? (yes/no)")
        return True

    if step == "visa":
        state["visa_required"] = text.strip().lower().startswith("y")
        state["step"] = "accommodation"
        send_message(chat_id, "Do you require accommodation? (yes/no)")
        return True

    if step == "accommodation":
        state["accommodation_required"] = text.strip().lower().startswith("y")
        agents = load_agents()
        agents.append({
            "id": next_agent_id(agents),
            "name": state.get("name") or "Job seeker",
            "telegram_username": state.get("username") or "",
            "telegram_chat_id": chat_id,
            "countries": state.get("countries", []),
            "job_titles": state.get("job_titles", []),
            "min_salary": state.get("min_salary", 0),
            "visa_required": state.get("visa_required", False),
            "accommodation_required": state.get("accommodation_required", False),
            "created_at": _now_iso(),
            "active": True,
        })
        save_agents(agents)
        del _pending_setup[chat_id]
        send_message(chat_id, "✅ Your agent is set up! I'll start sending matches as soon as I find them.\n\n" + HELP_TEXT)
        return True

    return False


# ---------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------
def dispatch(message: Dict[str, Any]) -> None:
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    username = message["chat"].get("username", "")

    if not text:
        return

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        payload = parts[1].strip() if len(parts) > 1 else ""
        handle_start(chat_id, username, payload)
        return

    if text.startswith("/help"):
        send_message(chat_id, HELP_TEXT)
        return

    # Mid-onboarding free text takes priority over command lookup
    if chat_id in _pending_setup and continue_onboarding(chat_id, text):
        return

    agent = find_agent_by_chat_id(chat_id)
    if not agent:
        send_message(chat_id, "Please send /start first to set up your job agent.")
        return

    command = text.split()[0].lower()
    if command == "/jobs":
        handle_jobs(chat_id, agent)
    elif command == "/matches":
        handle_matches(chat_id, agent)
    elif command == "/report":
        handle_report(chat_id, agent)
    elif command == "/visa":
        handle_visa(chat_id, agent)
    else:
        send_message(chat_id, "I didn't recognize that command.\n\n" + HELP_TEXT)


def run_polling_loop() -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set. See docs/TELEGRAM_BOT_GUIDE.md")
        return

    print("GulfJobs AI Agent bot running (long polling)...")
    offset = 0
    while True:
        try:
            resp = requests.get(
                f"{API_BASE}/getUpdates",
                params={"timeout": POLL_TIMEOUT, "offset": offset},
                timeout=POLL_TIMEOUT + 10,
            )
            resp.raise_for_status()
            data = resp.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message")
                if message:
                    dispatch(message)
        except requests.RequestException as e:
            print(f"Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_polling_loop()
