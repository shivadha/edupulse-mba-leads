"""
EduPulse CAT College Predictor — pure prediction logic + lead capture storage.

Self-contained: does NOT touch database.py. colleges.json is the baked,
runtime dataset (parsed once from pathak0806/mba-eligify's
CatScore_MBA_Dataset.xlsx). predictor_leads lives in the same
data/edupulse.db file as the rest of the app, created lazily.
"""

import json
import os
import sqlite3
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_HERE, "data")
COLLEGES_PATH = os.path.join(DATA_DIR, "colleges.json")
DB_PATH = os.path.join(DATA_DIR, "edupulse.db")

# Tagging bands (percentile minus the college's category cutoff)
SAFE_MARGIN = 3.0    # cutoff at least 3 points below your percentile -> safe
REACH_STRETCH = 2.0 # show colleges up to 2 points above your percentile -> reach

TIER_RANK = {"Tier 1": 1, "Tier 2": 2, "Tier 3": 3}

_categories = ("General", "EWS", "OBC", "SC", "ST")


def load_colleges():
    with open(COLLEGES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _effective_cutoff(college, category):
    """Category-aware cutoff. Falls back to the General cutoff."""
    cat = category if category in _categories else "General"
    cutoffs = college.get("cutoffs") or {}
    return float(cutoffs.get(cat, college.get("cutoff_percentile", 0)) or 0)


def predict(cat_percentile, category="General", workex_months=0, gender="male"):
    """Return colleges the aspirant has a shot at, tagged reach/target/safe.

    - Eligible: category cutoff <= percentile (real per-category cutoffs
      from the dataset — no fabricated relaxation).
    - Reach: cutoff up to REACH_STRETCH points above percentile (aspirational).
    - Sorted by tier (best first), then cutoff (highest first).

    workex_months / gender are accepted for the counselor handoff and future
    diversity-weight scoring; they do not currently shift cutoffs.
    """
    pct = max(0.0, min(100.0, float(cat_percentile)))
    results = []
    for c in load_colleges():
        cutoff = _effective_cutoff(c, category)
        gap = pct - cutoff  # positive = your percentile clears the cutoff
        if gap < -REACH_STRETCH:
            continue
        tag = "safe" if gap >= SAFE_MARGIN else "target" if gap >= 0 else "reach"
        results.append({
            "name": c["name"],
            "city": c.get("city", ""),
            "tier": c.get("tier", ""),
            "cutoff": round(cutoff, 1),
            "avg_package_lpa": c.get("avg_package_lpa"),
            "fees_lakhs": c.get("fees_lakhs"),
            "tag": tag,
            "gap": round(gap, 1),
        })
    results.sort(key=lambda r: (TIER_RANK.get(r["tier"], 9), -r["cutoff"], r["name"]))
    return results


# ── Lead capture (own table, own connection — no database.py changes) ──────

def ensure_schema():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS predictor_leads (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   name TEXT NOT NULL,
                   phone TEXT NOT NULL,
                   cat_percentile REAL,
                   category TEXT,
                   created_at TEXT NOT NULL
               )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predictor_leads_phone "
            "ON predictor_leads(phone)"
        )
        conn.commit()
    finally:
        conn.close()


_PHONE_RE = None

def _valid_phone(phone):
    import re
    global _PHONE_RE
    if _PHONE_RE is None:
        _PHONE_RE = re.compile(r"^[6-9]\d{9}$")
    p = re.sub(r"[\s\-+]", "", str(phone or ""))
    if p.startswith("91") and len(p) == 12:
        p = p[2:]
    return p if _PHONE_RE.match(p) else None


def save_lead(name, phone, cat_percentile=None, category="General"):
    """Validate and store a predictor lead. Returns (ok, payload)."""
    clean = _valid_phone(phone)
    if not clean:
        return False, {"error": "Enter a valid 10-digit Indian mobile number."}
    name = str(name or "").strip()
    if len(name) < 2:
        return False, {"error": "Please enter your name."}
    ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            "INSERT INTO predictor_leads (name, phone, cat_percentile, category, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (name[:120], clean,
             float(cat_percentile) if cat_percentile is not None else None,
             category if category in _categories else "General",
             time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        conn.commit()
        return True, {"id": cur.lastrowid}
    finally:
        conn.close()


def count_leads():
    ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute("SELECT COUNT(*) FROM predictor_leads").fetchone()[0]
    finally:
        conn.close()
