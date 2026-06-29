# Telegram Bot Integration Guide

## 1. Create your bot with @BotFather

1. Open Telegram, search for **@BotFather**.
2. Send `/newbot`.
3. Pick a display name, e.g. `GulfJobs AI Agent`.
4. Pick a unique username ending in `bot`, e.g. `GulfJobsAIAgent_bot`. This is the `BOT_USERNAME` used in `assets/js/create-agent.js` for the Telegram deep link — update that constant to match.
5. BotFather replies with a **bot token**, e.g. `123456789:AAH4w...`. Copy it — never commit it to the repo.

## 2. Store the token as a GitHub secret (for scheduled alerts)

1. Repository → **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `TELEGRAM_BOT_TOKEN`, value: your token from BotFather. Save.

`.github/workflows/daily-job-search.yml` reads this automatically and uses it in `bot/notifier.py` to push outbound job alerts and daily reports.

## 3. Run the interactive bot (for /jobs, /matches, /report, /visa, /help, and /start registration)

GitHub Actions runs on a **schedule** — it doesn't stay alive 24/7 to listen for incoming messages. `bot/telegram_bot.py` needs to run continuously somewhere else.

### Option A — your own computer (simplest, for testing)
```bash
cd bot
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="123456789:AAH4w...your-token..."
python telegram_bot.py
```
Leave the terminal open — the bot answers as long as this runs.

### Option B — a free always-on host (recommended for production)
Railway, Render, or Fly.io all have free tiers. Steps are the same shape on any of them:
1. Create a new background "worker" service (not a web service) pointing at this repo.
2. Start command: `pip install -r bot/requirements.txt && python bot/telegram_bot.py`
3. Add an environment variable `TELEGRAM_BOT_TOKEN` with your token.
4. Deploy. The bot now runs continuously.

### Option C — your own always-on machine / Raspberry Pi
Same as Option A, run inside `systemd`, `pm2`, or `tmux`/`screen` so it survives reboots.

## 4. How registration actually works (two paths, both supported)

**Path 1 — Telegram deep link (preferred, instant):**
When someone finishes `create-agent.html`, the page builds a link like `https://t.me/GulfJobsAIAgent_bot?start=eyJ2...`. Tapping it opens Telegram with that payload pre-filled after `/start`. The bot decodes it (countries, titles, salary, visa/accommodation preferences) and immediately saves a new entry into `data/agents.json` with the chat's numeric `telegram_chat_id` — no manual editing required.

**Path 2 — Conversational fallback:**
If the encoded preferences are too long for Telegram's 64-character start-parameter limit (lots of countries/titles picked), the link falls back to `?start=setup`. The bot then asks short follow-up questions (name → countries → titles → salary → visa → accommodation) directly in chat and saves the agent the same way.

Either path writes `telegram_chat_id` onto the agent record, which is what `bot/notifier.py` uses to know where to send alerts.

## 5. Testing end to end

1. Run `bot/telegram_bot.py` locally (Option A).
2. Open `create-agent.html` in a browser, fill the form, and tap **Activate on Telegram** on the success screen.
3. Confirm you get a welcome message back in Telegram.
4. Try `/jobs`, `/matches`, `/report`, `/visa`, `/help`.
5. To test scheduled push alerts, run `python bot/notifier.py` locally with `TELEGRAM_BOT_TOKEN` set — you should receive Telegram messages for any new high-match jobs (score 70+) that haven't been sent to you before.

## 6. Command reference

| Command    | What it does                                              |
|------------|------------------------------------------------------------|
| `/start`   | Registers/links this Telegram chat to a job agent profile  |
| `/jobs`    | Shows the 5 most recently posted jobs                      |
| `/matches` | Shows your top 5 jobs scoring 45+                           |
| `/report`  | Generates an on-demand daily report                         |
| `/visa`    | Shows jobs that mention visa sponsorship / work permits     |
| `/help`    | Lists all available commands                                |

## Troubleshooting

- **Bot doesn't reply at all** — `telegram_bot.py` isn't running anywhere (it never runs inside GitHub Actions).
- **"Please send /start first"** — your agent has no `telegram_chat_id` yet; send `/start` once.
- **No daily Telegram alerts** — check the `TELEGRAM_BOT_TOKEN` secret and the workflow logs under the Actions tab.
- **Deep link opens Telegram but nothing happens** — double-check `BOT_USERNAME` in `assets/js/create-agent.js` matches your real bot's username exactly.
