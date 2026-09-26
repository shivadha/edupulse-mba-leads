# Phase 2 — Counselor Alerts Setup

Every 5 minutes the scheduler scrapes; when a **high-intent** item lands
(`intent_level='high'` or `intent_score>=70`), the counselor gets an instant
Telegram message. All free, no SDKs.

## 1. Create the bot (one time, ~3 min)

1. Open Telegram, message **@BotFather**, send `/newbot`, follow the prompts.
2. BotFather replies with a **bot token** like `123456:ABC-DEF...` — copy it.
3. Message **@userinfobot** (or your new bot, send `/start` there) to get your
   **chat id** (a number like `5312511086`).

## 2. Set environment variables (the ONE thing you must do)

Alerts fire only if these are set in the terminal that runs the app:

```bash
# Windows (PowerShell)
$env:EDUPULSE_TG_BOT_TOKEN = "paste-token-here"
$env:EDUPULSE_TG_CHAT_ID   = "paste-chat-id-here"
python app.py

# Linux / Mac
export EDUPULSE_TG_BOT_TOKEN="paste-token-here"
export EDUPULSE_TG_CHAT_ID="paste-chat-id-here"
python app.py
```

Without them the app runs normally — alerts are just skipped and logged as
`skipped` in the `alert_log` table (no crash, no spam).

## 3. Test it

```bash
curl -X POST http://localhost:5050/api/alerts/test
```

- `{"sent": true}` → check Telegram, the ping arrived.
- `{"sent": false, "detail": "telegram not configured..."}` → env vars missing.

Recent alerts (last 20, newest first):

```bash
curl http://localhost:5050/api/alerts/recent
```

## 4. What the counselor gets

```
🔥 HIGH-INTENT LEAD (score 85)
📌 Need help choosing between XIMB and NMIMS...
📍 XIMB · via reddit
💬 snippet of the post...
🔗 https://...
```

Each lead alerts **once** (`alert_log` dedupes by `intel_id`).

## 5. Reply drafts (no LLM needed)

`alerts.draft_reply(intel_row)` returns 3 WhatsApp-ready templates:
first-touch opener, follow-up nudge, and a "fees too high" objection handler.
Counselor copies, personalizes, sends.

## 6. Optional: CallMeBot WhatsApp fallback

Only if you want WhatsApp instead of/in addition to Telegram:

1. WhatsApp `I allow callmebot to send me messages` to **+34 644 59 71 67**.
2. You get an API key back by reply (~2 min).
3. Set `EDUPULSE_CALLMEBOT_PHONE=91<10-digit>` and
   `EDUPULSE_CALLMEBOT_APIKEY=<key>`.

Fallback is attempted only when the Telegram send fails; nothing is required.

## 7. Run locally

```bash
cd edupulse-mba-leads
# (set the env vars from step 2 first)
pip install -r requirements.txt
python app.py          # http://localhost:5050
```

The scheduler thread inside `app.py` runs the scrape → score → alert loop
automatically. `alerts_routes.alerts_bp` must be registered in `app.py`
(handled during integration).
