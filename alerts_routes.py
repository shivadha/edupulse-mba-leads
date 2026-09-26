"""
EduPulse India — Phase 2 alerts API.
Parent agent registers `alerts_bp` in app.py (NOT done here).
"""

import logging
import os
import sqlite3
from flask import Blueprint, jsonify

import alerts

logger = logging.getLogger("edupulse.alerts_routes")

alerts_bp = Blueprint("alerts", __name__)


def _db_path() -> str:
    import database as db
    return db.DB_PATH


RECENT_SQL = """
SELECT a.id, a.intel_id, a.level, a.sent_at, a.channel, a.status,
       i.title, i.source, i.url, i.intent_score
FROM alert_log a
LEFT JOIN intelligence i ON i.id = a.intel_id
ORDER BY a.id DESC
LIMIT 20
"""


@alerts_bp.get("/api/alerts/recent")
def recent_alerts():
    """Last 20 alerts, newest first."""
    try:
        alerts.ensure_schema(_db_path())
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in conn.execute(RECENT_SQL)]
        finally:
            conn.close()
        return jsonify({"ok": True, "alerts": rows})
    except Exception as exc:
        logger.error("[Alerts] /api/alerts/recent failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


@alerts_bp.post("/api/alerts/test")
def test_alert():
    """Send a test ping to the counselor. Never crashes."""
    try:
        text = (
            "✅ EduPulse alerts test — this is a test ping.\n"
            "High-intent leads will land here in real time."
        )
        ok, detail = alerts.send_telegram(
            os.environ.get("EDUPULSE_TG_BOT_TOKEN", "").strip(),
            os.environ.get("EDUPULSE_TG_CHAT_ID", "").strip(),
            text,
        )
        return jsonify({
            "ok": True,
            "channel": "telegram",
            "sent": ok,
            "detail": detail,
            "configured": bool(
                os.environ.get("EDUPULSE_TG_BOT_TOKEN")
                and os.environ.get("EDUPULSE_TG_CHAT_ID")
            ),
        })
    except Exception as exc:
        logger.error("[Alerts] /api/alerts/test failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500
