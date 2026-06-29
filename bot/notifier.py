"""
bot/notifier.py
-----------------------------------------------------------------------
The script executed by .github/workflows/daily-job-search.yml on a
schedule. It:

  1. Refreshes the job pool (scripts/scraper.py)
  2. Loads every registered agent from data/agents.json
  3. Scores every job for every agent (scripts/match_engine.py)
  4. Flags scams (scripts/scam_detector.py)
  5. Filters out jobs already sent to that agent (data/sent_log.json)
  6. Sends a Telegram message for every new high-match job (score 70+)
  7. Updates data/sent_log.json so jobs are never sent twice
  8. Writes a daily summary to data/reports.json

Requires only the standard library + `requests`. Set TELEGRAM_BOT_TOKEN
as an environment variable / GitHub secret before running.
-----------------------------------------------------------------------
"""

from __future__ import annotations
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

sys.path.append(str(Path(__file__).resolve().parent.parent / "scripts"))
from scraper import fetch_all_jobs, save_jobs  # noqa: E402
from match_engine import compute_match_score, score_label  # noqa: E402
from scam_detector import detect_visa_sponsorship, detect_scam  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
AGENTS_FILE = DATA_DIR / "agents.json"
SENT_LOG_FILE = DATA_DIR / "sent_log.json"
REPORTS_FILE = DATA_DIR / "reports.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

HIGH_MATCH_THRESHOLD = 70


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def send_message(chat_id: int, text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        print(f"[DRY RUN — TELEGRAM_BOT_TOKEN not set] -> {chat_id}:\n{text}\n")
        return False
    try:
        resp = requests.post(
            f"{API_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Telegram send failed for chat_id={chat_id}: {e}")
        return False


def enrich_job(job: Dict[str, Any], agent: Dict[str, Any]) -> Dict[str, Any]:
    visa_info = detect_visa_sponsorship(job)
    scam_info = detect_scam(job)
    score, breakdown = compute_match_score(job, agent)
    enriched = dict(job)
    enriched["visa_sponsorship"] = job.get("visa_sponsorship") or visa_info["detected"]
    enriched["scam_flagged"] = scam_info["isSuspicious"]
    enriched["scam_reasons"] = scam_info["reasons"]
    enriched["match_score"] = score
    enriched["match_breakdown"] = breakdown
    enriched["match_label"] = score_label(score)
    return enriched


def format_job_message(job: Dict[str, Any]) -> str:
    visa_line = "✅ Visa sponsorship" if job["visa_sponsorship"] else "❌ No visa sponsorship mentioned"
    accom_line = "✅ Accommodation" if job.get("accommodation") else "❌ No accommodation mentioned"
    return (
        f"🎯 *New high match! Score: {job['match_score']}/100*\n\n"
        f"*{job['title']}* — {job['company']}\n"
        f"📍 {job.get('city', '')}, {job['country']}\n"
        f"💰 ${job.get('salary_min', '?')}–{job.get('salary_max', '?')}/mo\n"
        f"{visa_line}\n{accom_line}\n\n"
        f"🔗 {job.get('url', '')}\n"
        f"Source: {job.get('source', 'Unknown')}"
    )


def format_report_message(report: Dict[str, Any]) -> str:
    best = report.get("best_opportunity")
    best_line = "No matches yet." if not best else f"{best['title']} — {best['company']} ({best['country']}), score {best['match_score']}/100"
    return (
        f"📊 *Daily Report — {report['date']}*\n\n"
        f"Total jobs found: {report['total_jobs_found']}\n"
        f"High matches: {report['high_matches']}\n"
        f"Visa-sponsored jobs: {report['visa_sponsored_jobs']}\n"
        f"Scam jobs flagged: {report['scam_jobs_flagged']}\n\n"
        f"🏆 Best opportunity: {best_line}"
    )


def run() -> None:
    print("Step 1/6 — Refreshing job pool...")
    jobs = fetch_all_jobs(new_mock_count=3)
    save_jobs(jobs)
    print(f"  -> {len(jobs)} total jobs in pool")

    print("Step 2/6 — Loading agents...")
    agents = [a for a in load_json(AGENTS_FILE, []) if a.get("active", True)]
    print(f"  -> {len(agents)} active agents")

    sent_log = load_json(SENT_LOG_FILE, {"sent": {}})
    sent_map: Dict[str, List[str]] = sent_log.get("sent", {})

    overall_total = len(jobs)
    overall_visa = 0
    overall_scam = 0
    overall_high = 0
    overall_best: Optional[Dict[str, Any]] = None
    overall_best_score = -1

    for agent in agents:
        agent_id = agent["id"]
        print(f"Step 3/6 — Matching jobs for {agent.get('name')} ({agent_id})...")

        enriched = [enrich_job(j, agent) for j in jobs]
        already_sent = set(sent_map.get(agent_id, []))
        candidates = [j for j in enriched if j["id"] not in already_sent and not j["scam_flagged"]]
        high_matches = [j for j in candidates if j["match_score"] >= HIGH_MATCH_THRESHOLD]

        chat_id = agent.get("telegram_chat_id")
        sent_count = 0
        if chat_id:
            for job in sorted(high_matches, key=lambda j: -j["match_score"]):
                if send_message(chat_id, format_job_message(job)):
                    sent_count += 1
        else:
            print(f"  -> No telegram_chat_id stored for @{agent.get('telegram_username')}; "
                  f"they need to send /start to the bot once.")

        sent_map.setdefault(agent_id, [])
        sent_map[agent_id] = list(set(sent_map[agent_id] + [j["id"] for j in candidates]))

        agent_visa = sum(1 for j in enriched if j["visa_sponsorship"] and not j["scam_flagged"])
        agent_scam = sum(1 for j in enriched if j["scam_flagged"])
        agent_high = sum(1 for j in enriched if j["match_label"] == "high" and not j["scam_flagged"])
        best_for_agent = max((j for j in enriched if not j["scam_flagged"]), key=lambda j: j["match_score"], default=None)

        overall_visa = max(overall_visa, agent_visa)
        overall_scam = max(overall_scam, agent_scam)
        overall_high = max(overall_high, agent_high)
        if best_for_agent and best_for_agent["match_score"] > overall_best_score:
            overall_best_score = best_for_agent["match_score"]
            overall_best = best_for_agent

        if chat_id:
            agent_report = {
                "date": date.today().isoformat(),
                "total_jobs_found": overall_total,
                "high_matches": agent_high,
                "visa_sponsored_jobs": agent_visa,
                "scam_jobs_flagged": agent_scam,
                "best_opportunity": None if not best_for_agent else {
                    "id": best_for_agent["id"], "title": best_for_agent["title"],
                    "company": best_for_agent["company"], "country": best_for_agent["country"],
                    "match_score": best_for_agent["match_score"],
                },
            }
            send_message(chat_id, format_report_message(agent_report))

        print(f"  -> {len(candidates)} new jobs, {len(high_matches)} high matches, {sent_count} Telegram messages sent")

    print("Step 4/6 — Saving duplicate-detection log...")
    save_json(SENT_LOG_FILE, {"sent": sent_map})

    print("Step 5/6 — Writing daily report...")
    reports_payload = load_json(REPORTS_FILE, {"reports": []})
    reports_payload.setdefault("reports", [])
    reports_payload["reports"].append({
        "date": date.today().isoformat(),
        "total_jobs_found": overall_total,
        "high_matches": overall_high,
        "visa_sponsored_jobs": overall_visa,
        "scam_jobs_flagged": overall_scam,
        "best_opportunity": None if not overall_best else {
            "id": overall_best["id"], "title": overall_best["title"],
            "company": overall_best["company"], "country": overall_best["country"],
            "match_score": overall_best["match_score"],
        },
    })
    save_json(REPORTS_FILE, reports_payload)

    print("Step 6/6 — Done.")


if __name__ == "__main__":
    run()
