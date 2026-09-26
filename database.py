"""
EduPulse India — SQLite database layer
Stores leads and scraped intelligence data.
"""

import sqlite3
import os
import json
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "edupulse.db")


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables on first run."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = _connect()
    c = conn.cursor()

    # --- LEADS (form submissions) ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        phone       TEXT NOT NULL,
        email       TEXT,
        city        TEXT,
        target_exam TEXT,
        target_year TEXT,
        source      TEXT DEFAULT 'landing_page',
        utm         TEXT,
        whatsapp_sent INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT (datetime('now'))
    )""")

    # --- SCRAPED INTELLIGENCE ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS intelligence (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        uid         TEXT UNIQUE,
        source      TEXT,
        title       TEXT,
        snippet     TEXT,
        url         TEXT,
        college     TEXT,
        exam_hint   TEXT,
        city_hint   TEXT,
        extra_json  TEXT,
        scraped_at  TEXT
    )""")

    # --- SCRAPE LOG ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS scrape_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at      TEXT,
        items_added INTEGER,
        duration_s  REAL
    )""")

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# LEAD CRUD
# ---------------------------------------------------------------------------
def save_lead(name: str, phone: str, email: str, city: str,
              target_exam: str, target_year: str, utm: str = None) -> int:
    conn = _connect()
    c = conn.cursor()
    c.execute("""
        INSERT INTO leads (name, phone, email, city, target_exam, target_year, utm)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, phone, email, city, target_exam, target_year, utm))
    row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_leads(limit: int = 200, exam_filter: str = None) -> list[dict]:
    conn = _connect()
    c = conn.cursor()
    if exam_filter and exam_filter != "all":
        rows = c.execute(
            "SELECT * FROM leads WHERE target_exam=? ORDER BY id DESC LIMIT ?",
            (exam_filter, limit)
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lead_stats() -> dict:
    conn = _connect()
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    today = c.execute(
        "SELECT COUNT(*) FROM leads WHERE date(created_at)=date('now')"
    ).fetchone()[0]
    by_exam = c.execute(
        "SELECT target_exam, COUNT(*) as cnt FROM leads GROUP BY target_exam ORDER BY cnt DESC"
    ).fetchall()
    by_city = c.execute(
        "SELECT city, COUNT(*) as cnt FROM leads WHERE city!='' GROUP BY city ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    
    # Intelligence metrics
    intel_total = c.execute("SELECT COUNT(*) FROM intelligence").fetchone()[0]
    intel_today = c.execute(
        "SELECT COUNT(*) FROM intelligence WHERE date(scraped_at)=date('now')"
    ).fetchone()[0]
    intel_by_exam = c.execute(
        "SELECT exam_hint, COUNT(*) as cnt FROM intelligence WHERE exam_hint IS NOT NULL AND exam_hint != '' GROUP BY exam_hint ORDER BY cnt DESC"
    ).fetchall()
    intel_by_source = c.execute(
        "SELECT source, COUNT(*) as cnt FROM intelligence GROUP BY source ORDER BY cnt DESC"
    ).fetchall()
    intel_by_city = c.execute(
        "SELECT city_hint, COUNT(*) as cnt FROM intelligence WHERE city_hint IS NOT NULL AND city_hint != '' GROUP BY city_hint ORDER BY cnt DESC LIMIT 10"
    ).fetchall()

    conn.close()

    # If manual leads are 0, use intelligence exam/city breakdown for charts
    display_by_exam = [dict(r) for r in by_exam] if by_exam else [{"target_exam": r[0], "cnt": r[1]} for r in intel_by_exam]
    display_by_city = [dict(r) for r in by_city] if by_city else [{"city": r[0], "cnt": r[1]} for r in intel_by_city]

    return {
        "total": total,
        "today": today,
        "intel_total": intel_total,
        "intel_today": intel_today,
        "by_exam": display_by_exam,
        "by_city": display_by_city,
        "intel_by_exam": [{"exam": r[0], "cnt": r[1]} for r in intel_by_exam],
        "intel_by_source": [{"source": r[0], "cnt": r[1]} for r in intel_by_source],
    }


def convert_intel_to_lead(intel_id: int, name: str = "", phone: str = "", notes: str = "") -> int:
    """Converts a scraped intelligence item into an actionable CRM lead."""
    conn = _connect()
    c = conn.cursor()
    intel = c.execute("SELECT * FROM intelligence WHERE id=?", (intel_id,)).fetchone()
    if not intel:
        conn.close()
        return 0
    intel_dict = dict(intel)
    lead_name = name or (intel_dict.get("title", "")[:40] or "MBA Aspirant")
    lead_phone = phone or "Pending Followup"
    lead_city = intel_dict.get("city_hint") or "India"
    lead_exam = intel_dict.get("exam_hint") or "CAT"
    utm = f"scraped:{intel_dict.get('source')}"
    
    c.execute("""
        INSERT INTO leads (name, phone, email, city, target_exam, target_year, utm)
        VALUES (?, ?, ?, ?, ?, '2025-2026', ?)
    """, (lead_name, lead_phone, "", lead_city, lead_exam, utm))
    lead_id = c.lastrowid
    conn.commit()
    conn.close()
    return lead_id


def mark_whatsapp_sent(lead_id: int):
    conn = _connect()
    conn.execute("UPDATE leads SET whatsapp_sent=1 WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# INTELLIGENCE CRUD
# ---------------------------------------------------------------------------
def save_intelligence_batch(items: list[dict]) -> int:
    """Insert new items, skip duplicates by uid. Returns count inserted."""
    conn = _connect()
    c = conn.cursor()
    inserted = 0
    for item in items:
        try:
            extra = {k: v for k, v in item.items()
                     if k not in ("uid", "source", "title", "snippet", "url",
                                  "college", "exam_hint", "city_hint", "scraped_at")}
            c.execute("""
                INSERT OR IGNORE INTO intelligence
                    (uid, source, title, snippet, url, college, exam_hint, city_hint, extra_json, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get("uid"), item.get("source"), item.get("title"),
                item.get("snippet"), item.get("url"), item.get("college"),
                item.get("exam_hint"), item.get("city_hint"),
                json.dumps(extra), item.get("scraped_at"),
            ))
            if c.rowcount:
                inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return inserted


def get_intelligence(limit: int = 100, source: str = None, exam: str = None) -> list[dict]:
    conn = _connect()
    c = conn.cursor()
    query = "SELECT * FROM intelligence WHERE 1=1"
    params = []
    if source and source != "all":
        query += " AND source=?"
        params.append(source)
    if exam and exam != "all":
        query += " AND exam_hint=?"
        params.append(exam)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = c.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_scrape_run(items_added: int, duration_s: float):
    conn = _connect()
    conn.execute(
        "INSERT INTO scrape_log (run_at, items_added, duration_s) VALUES (datetime('now'), ?, ?)",
        (items_added, duration_s)
    )
    conn.commit()
    conn.close()


def get_last_scrape_time() -> str:
    conn = _connect()
    row = conn.execute("SELECT run_at FROM scrape_log ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row[0] if row else "Never"


def get_intelligence_count() -> int:
    conn = _connect()
    count = conn.execute("SELECT COUNT(*) FROM intelligence").fetchone()[0]
    conn.close()
    return count


def get_db_summary() -> dict:
    """Quick DB health check — total rows per table."""
    conn = _connect()
    intel  = conn.execute("SELECT COUNT(*) FROM intelligence").fetchone()[0]
    leads  = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    runs   = conn.execute("SELECT COUNT(*) FROM scrape_log").fetchone()[0]
    by_src = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM intelligence GROUP BY source ORDER BY cnt DESC"
    ).fetchall()
    last   = conn.execute(
        "SELECT run_at, items_added FROM scrape_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "intelligence_total": intel,
        "leads_total": leads,
        "scrape_runs": runs,
        "by_source": [dict(r) for r in by_src],
        "last_run": dict(last) if last else None,
    }
