"""
EduPulse India — Phase 2: counselor real-time alerts + reply drafting.

Watches the `intelligence` table for high-intent items (intent_level='high'
or intent_score>=70, Phase 1) and pings the counselor the moment a new one
lands. All $0:

  1. Telegram Bot API direct POST — primary channel (free, unlimited).
  2. CallMeBot WhatsApp — optional fallback, only if its env vars are set.

Config (env vars — nothing is required for the app to run; if unset,
alerts are skipped gracefully and logged):
  EDUPULSE_TG_BOT_TOKEN   Telegram bot token from @BotFather
  EDUPULSE_TG_CHAT_ID     Counselor's chat id (message @userinfobot)
  EDUPULSE_CALLMEBOT_PHONE   e.g. 9198XXXXXXXX (fallback only)
  EDUPULSE_CALLMEBOT_APIKEY  from CallMeBot's WhatsApp setup

Schema here is self-contained: database.py is NOT touched.
"""

import logging
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime

logger = logging.getLogger("edupulse.alerts")

ALERT_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    intel_id INTEGER,
    level    TEXT,
    sent_at  TEXT,
    channel  TEXT,
    status   TEXT
)
"""

HIGH_INTENT_SQL = """
SELECT id, source, title, snippet, url, college, exam_hint, city_hint, intent_level, intent_score
FROM intelligence
WHERE (intent_level = 'high' OR intent_score >= 70)
  AND id NOT IN (SELECT intel_id FROM alert_log WHERE status = 'sent')
ORDER BY intent_score DESC, id DESC
"""

TEMPLATES = {
    "first_touch": (
        "Hi {name}! Noticed you were looking into {college_hint} admissions — "
        "I help students pick the right MBA college in {city_hint}. "
        "Free 10-min guidance call, no spam, no obligation. Interested? "
        "— EduPulse Counseling"
    ),
    "followup_nudge": (
        "Hi {name}, just bumping this up — admissions for {college_hint} are "
        "moving fast and the best scholarship windows close early. "
        "Worth a quick 5-min chat to check your options? — EduPulse"
    ),
    "objection_fees": (
        "Totally fair question! Fees vary a lot — several good colleges in {city_hint} "
        "come in under ₹{fee_hint}L total with scholarships based on your CAT/CET score. "
        "I can share a realistic cost-vs-ROI comparison for 3-4 options. Want it? — EduPulse"
    ),
}


def ensure_schema(db_path: str) -> None:
    """Create the alert_log table if missing (self-contained, no database.py edit)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(ALERT_LOG_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def send_telegram(bot_token: str, chat_id: str, text: str) -> tuple[bool, str]:
    """
    Send via Telegram Bot API (stdlib, free). Returns (ok, detail).
    Never raises — returns (False, reason) on any failure.
    """
    if not bot_token or not chat_id:
        return False, "telegram not configured (EDUPULSE_TG_BOT_TOKEN / EDUPULSE_TG_CHAT_ID unset)"
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(200).decode("utf-8", "replace")
        if resp.status == 200 and '"ok":true' in body:
            return True, "ok"
        return False, f"telegram api returned {resp.status}: {body[:120]}"
    except Exception as exc:  # network, bad token, proxy, etc.
        return False, f"telegram error: {exc}"


def send_callmebot(phone: str, api_key: str, text: str) -> tuple[bool, str]:
    """Optional CallMeBot WhatsApp fallback. Returns (ok, detail). Never raises."""
    if not phone or not api_key:
        return False, "callmebot not configured (EDUPULSE_CALLMEBOT_PHONE / EDUPULSE_CALLMEBOT_APIKEY unset)"
    try:
        url = (
            "https://api.callmebot.com/whatsapp.php?"
            + urllib.parse.urlencode({"phone": phone, "text": text, "apikey": api_key})
        )
        with urllib.request.urlopen(url, timeout=25) as resp:
            body = resp.read(300).decode("utf-8", "replace")
        if resp.status == 200:
            return True, f"ok: {body[:120]}"
        return False, f"callmebot returned {resp.status}: {body[:120]}"
    except Exception as exc:
        return False, f"callmebot error: {exc}"


def format_alert(row: dict) -> str:
    """Short counselor message for one high-intent item."""
    title = (row.get("title") or "New lead signal")[:120]
    snippet = (row.get("snippet") or "")[:200]
    source = row.get("source") or "web"
    score = row.get("intent_score") or 0
    college = row.get("college") or row.get("exam_hint") or "MBA"
    url = row.get("url") or ""
    lines = [
        f"🔥 HIGH-INTENT LEAD (score {score})",
        f"📌 {title}",
        f"📍 {college} · via {source}",
    ]
    if snippet:
        lines.append(f"💬 {snippet}")
    if url:
        lines.append(f"🔗 {url}")
    return "\n".join(lines)


def draft_reply(intel_row: dict) -> list[str]:
    """
    2-3 short counselor reply templates for a lead row.
    Plain strings, no LLM needed — WhatsApp-ready.
    """
    row = intel_row or {}
    ctx = {
        "name": "there",
        "college_hint": row.get("college") or row.get("exam_hint") or "MBA admissions",
        "city_hint": row.get("city_hint") or "your city",
        "fee_hint": "8-12",
    }
    return [
        TEMPLATES["first_touch"].format(**ctx),
        TEMPLATES["followup_nudge"].format(**ctx),
        TEMPLATES["objection_fees"].format(**ctx),
    ]


def _record_alert(conn: sqlite3.Connection, intel_id: int, level: str, channel: str, status: str) -> None:
    conn.execute(
        "INSERT INTO alert_log (intel_id, level, sent_at, channel, status) VALUES (?, ?, ?, ?, ?)",
        (intel_id, level, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), channel, status),
    )


def check_and_alert(db_path: str) -> dict:
    """
    Find un-alerted high-intent rows, send counselor alerts, log them.
    Returns {'checked': n, 'sent': n, 'skipped': n, 'errors': n}.
    Never raises on transport failures — records 'skipped'/'error' instead.
    """
    ensure_schema(db_path)
    result = {"checked": 0, "sent": 0, "skipped": 0, "errors": 0}

    tg_token = os.environ.get("EDUPULSE_TG_BOT_TOKEN", "").strip()
    tg_chat = os.environ.get("EDUPULSE_TG_CHAT_ID", "").strip()
    cb_phone = os.environ.get("EDUPULSE_CALLMEBOT_PHONE", "").strip()
    cb_key = os.environ.get("EDUPULSE_CALLMEBOT_APIKEY", "").strip()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(HIGH_INTENT_SQL)]
    finally:
        conn.close()
    result["checked"] = len(rows)
    if not rows:
        return result

    conn = sqlite3.connect(db_path)
    try:
        for row in rows:
            text = format_alert(row)
            level = row.get("intent_level") or "high"

            ok, detail = send_telegram(tg_token, tg_chat, text)
            channel = "telegram"
            if not ok:
                # Optional CallMeBot fallback — only attempted if its envs exist.
                if cb_phone and cb_key:
                    ok, detail = send_callmebot(cb_phone, cb_key, text)
                    channel = "whatsapp-callmebot"
                status = "sent" if ok else "skipped"
            else:
                status = "sent"

            if status == "sent":
                result["sent"] += 1
            elif "not configured" in detail:
                result["skipped"] += 1
            else:
                result["errors"] += 1

            logger.info("[Alerts] intel_id=%s channel=%s status=%s (%s)",
                        row["id"], channel, status, detail)
            _record_alert(conn, row["id"], level, channel, status)
            conn.commit()
            time.sleep(0.5)  # be polite to the Telegram API
    finally:
        conn.close()
    return result
