"""
EduPulse India — Flask Web Application
=========================================
Fixes in this version:
  - Scraper runs IMMEDIATELY on startup (background thread), then every 5 min
  - Uses scout's 3-tier fetch chain (fast HTTP -> stealth -> urllib fallback)
  - No "wait for first request" — data is populated as soon as server starts
  - All 13 sources integrated with proper error handling

Routes:
  GET  /                  — Landing page
  POST /submit-lead       — Save lead + WhatsApp
  GET  /admin             — Admin dashboard
  GET  /paid-leads        — Paid lead marketplace
  GET  /thank-you         — Post-registration page
  GET  /api/leads         — JSON leads list
  GET  /api/intelligence  — JSON scraped data feed
  GET  /api/stats         — JSON stats + scheduler + source list
  GET  /api/sources       — JSON list of all 13 scraper sources
  GET  /api/scheduler     — Scheduler status
  POST /api/scrape-now    — Trigger immediate background scrape
"""

import sys
import os
import logging
import threading

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, render_template, redirect, url_for
import database as db
import scheduler as sched
from whatsapp import send_lead_whatsapp

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("edupulse.app")

app = Flask(__name__, template_folder="templates", static_folder="static")

# Phase 2 + 3 blueprints (registered by parent agent; modules self-contained)
try:
    from alerts_routes import alerts_bp
    app.register_blueprint(alerts_bp)
except Exception as e:  # never let alerts break app boot
    logging.getLogger("edupulse.app").warning("alerts blueprint not loaded: %s", e)
try:
    from predictor_routes import predictor_bp
    app.register_blueprint(predictor_bp)
except Exception as e:
    logging.getLogger("edupulse.app").warning("predictor blueprint not loaded: %s", e)


# ---------------------------------------------------------------------------
# STARTUP — init DB + immediate scrape + background scheduler
# ---------------------------------------------------------------------------
def _startup():
    """Runs once in a background thread right after server starts."""
    logger.info("[Startup] Initializing database...")
    db.init_db()

    logger.info("[Startup] Running FIRST scrape immediately (background)...")
    try:
        from scraper.sources import run_all_scrapers
        items = run_all_scrapers()
        added = db.save_intelligence_batch(items)
        db.log_scrape_run(added, 0)
        logger.info("[Startup] First scrape done — %d items added to DB", added)
    except Exception as exc:
        logger.error("[Startup] First scrape failed: %s", exc)

    logger.info("[Startup] Starting 5-minute background scheduler...")
    sched.start(interval_seconds=300)
    logger.info("[Startup] All systems ready.")


# Fire startup in a background thread so Flask can start serving immediately
_startup_thread = threading.Thread(target=_startup, daemon=True, name="edupulse-startup")
_startup_thread.start()


# ---------------------------------------------------------------------------
# PRIMARY DASHBOARD (Internal Lead & Scraper Intelligence Portal)
# ---------------------------------------------------------------------------
@app.route("/")
@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/landing")
def landing():
    return render_template("landing.html")


# ---------------------------------------------------------------------------
# LEAD SUBMISSION
# ---------------------------------------------------------------------------
@app.route("/submit-lead", methods=["POST"])
def submit_lead():
    name        = request.form.get("name", "").strip()
    phone       = request.form.get("phone", "").strip()
    email       = request.form.get("email", "").strip()
    city        = request.form.get("city", "").strip()
    target_exam = request.form.get("target_exam", "").strip()
    target_year = request.form.get("target_year", "").strip()
    utm         = request.form.get("utm_source", "")

    if not name or not phone:
        return jsonify({"ok": False, "error": "Name and phone are required"}), 400

    lead_id = db.save_lead(name, phone, email, city, target_exam, target_year, utm)

    lead_data = {
        "id": lead_id, "name": name, "phone": phone,
        "email": email, "city": city,
        "target_exam": target_exam, "target_year": target_year,
    }
    threading.Thread(target=send_lead_whatsapp, args=(lead_data,), daemon=True).start()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
       (request.content_type and "json" in request.content_type):
        return jsonify({"ok": True, "lead_id": lead_id,
                        "message": "Registered! We'll reach out soon on WhatsApp."})
    return redirect(url_for("thank_you", name=name))


@app.route("/thank-you")
def thank_you():
    name = request.args.get("name", "there")
    return render_template("thank_you.html", name=name)


@app.route("/paid-leads")
def paid_leads():
    return render_template("paid_leads.html")


@app.route("/api/convert-lead", methods=["POST"])
def api_convert_lead():
    data = request.get_json(silent=True) or request.form
    intel_id = int(data.get("intel_id", 0))
    name = data.get("name", "")
    phone = data.get("phone", "")
    if not intel_id:
        return jsonify({"ok": False, "error": "intel_id required"}), 400
    lead_id = db.convert_intel_to_lead(intel_id, name, phone)
    return jsonify({"ok": True, "lead_id": lead_id, "message": "Successfully converted to CRM lead"})


@app.route("/api/export-leads")
def api_export_leads():
    import csv
    import io
    from flask import Response
    
    rows = db.get_intelligence(limit=5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Source", "Title / Inquiry", "Snippet", "Target Exam", "Target College", "City", "URL", "Scraped At"])
    for r in rows:
        writer.writerow([r.get("id"), r.get("source"), r.get("title"), r.get("snippet"), r.get("exam_hint"), r.get("college"), r.get("city_hint"), r.get("url"), r.get("scraped_at")])
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=edupulse_mba_leads.csv"}
    )


# ---------------------------------------------------------------------------
# JSON APIs
# ---------------------------------------------------------------------------
@app.route("/api/leads")
def api_leads():
    exam  = request.args.get("exam", "all")
    limit = min(int(request.args.get("limit", 200)), 500)
    return jsonify(db.get_leads(limit=limit, exam_filter=exam))


@app.route("/api/intelligence")
def api_intelligence():
    source = request.args.get("source", "all")
    exam   = request.args.get("exam", "all")
    limit  = min(int(request.args.get("limit", 100)), 500)
    data   = db.get_intelligence(limit=limit, source=source, exam=exam)
    return jsonify(data)


@app.route("/api/stats")
def api_stats():
    from scraper.sources import get_source_list
    stats = db.get_lead_stats()
    stats["last_scrape"] = db.get_last_scrape_time()
    stats["scheduler"]   = sched.status()
    stats["sources"]     = get_source_list()
    stats["intel_count"] = db.get_intelligence_count()
    return jsonify(stats)


@app.route("/api/sources")
def api_sources():
    from scraper.sources import get_source_list
    return jsonify(get_source_list())


@app.route("/api/scheduler")
def api_scheduler():
    return jsonify(sched.status())


@app.route("/api/scrape-now", methods=["POST"])
def api_scrape_now():
    """Trigger an immediate scrape in the background — non-blocking."""
    from scraper.sources import run_all_scrapers

    def _do():
        logger.info("[Manual scrape] Starting...")
        items = run_all_scrapers()
        added = db.save_intelligence_batch(items)
        db.log_scrape_run(added, 0)
        logger.info("[Manual scrape] Done — %d new items", added)

    threading.Thread(target=_do, daemon=True, name="manual-scrape").start()
    return jsonify({"ok": True, "message": "Scrape started in background — refresh in ~60s"})


@app.route("/api/db-stats")
def api_db_stats():
    """Quick DB health check endpoint."""
    conn_info = db.get_db_summary()
    return jsonify(conn_info)


@app.route("/api/health")
def api_health():
    """Phase 1: per-source scraper health + scheduler + high-intent counts."""
    from scraper.sources import get_source_list
    sources = {s["key"]: s for s in get_source_list()}
    health = []
    for h in db.get_source_health():
        key = h.get("source")
        meta = sources.get(key, {})
        health.append({
            "source": key,
            "label": meta.get("label", key),
            "healthy": h.get("last_error") is None and bool(h.get("last_ok")),
            "last_ok": h.get("last_ok"),
            "last_error": h.get("last_error"),
            "items_last_run": h.get("items_last_run"),
            "runs_ok": h.get("runs_ok"),
            "runs_fail": h.get("runs_fail"),
        })
    return jsonify({
        "ok": True,
        "scheduler": sched.status(),
        "last_scrape": db.get_last_scrape_time(),
        "sources": health,
        "high_intent_total": len(db.get_high_intent(limit=100000)),
    })


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  EduPulse India -- MBA Lead Generator")
    print("  Landing  : http://localhost:5050/")
    print("  Admin    : http://localhost:5050/admin")
    print("  Paid Leads: http://localhost:5050/paid-leads")
    print("  API      : http://localhost:5050/api/intelligence")
    print("  [Scraping starts in background automatically]")
    print("="*60 + "\n")
    app.run(host="0.0.0.0", port=5050, debug=False, use_reloader=False)
