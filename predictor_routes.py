"""
Predictor routes — Flask Blueprint. Registered by the parent agent in app.py::

    from predictor_routes import predictor_bp
    app.register_blueprint(predictor_bp)
"""

from flask import Blueprint, jsonify, render_template, request

from predictor import ensure_schema, predict, save_lead

predictor_bp = Blueprint("predictor", __name__)

_VALID_CATEGORIES = ("General", "EWS", "OBC", "SC", "ST")
_VALID_GENDERS = ("male", "female", "other")


@predictor_bp.route("/predictor", methods=["GET"])
def predictor_page():
    return render_template("predictor.html")


@predictor_bp.route("/api/predict", methods=["POST"])
def api_predict():
    data = request.get_json(force=True, silent=True) or {}
    try:
        pct = float(data.get("cat_percentile", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "cat_percentile must be a number between 0 and 100."}), 400
    if not (0 < pct <= 100):
        return jsonify({"error": "CAT percentile must be between 0 and 100."}), 400

    category = data.get("category", "General")
    if category not in _VALID_CATEGORIES:
        category = "General"
    gender = data.get("gender", "male")
    if gender not in _VALID_GENDERS:
        gender = "male"
    try:
        workex = max(0, int(data.get("workex_months", 0) or 0))
    except (TypeError, ValueError):
        workex = 0

    results = predict(pct, category=category, workex_months=workex, gender=gender)
    counts = {"safe": 0, "target": 0, "reach": 0}
    for r in results:
        counts[r["tag"]] += 1
    return jsonify({
        "percentile": pct,
        "category": category,
        "predictions": results,
        "counts": counts,
    })


@predictor_bp.route("/api/predict/lead", methods=["POST"])
def api_predict_lead():
    data = request.get_json(force=True, silent=True) or {}
    try:
        pct = float(data.get("cat_percentile")) if data.get("cat_percentile") is not None else None
    except (TypeError, ValueError):
        pct = None
    ok, payload = save_lead(
        name=data.get("name", ""),
        phone=data.get("phone", ""),
        cat_percentile=pct,
        category=data.get("category", "General"),
    )
    if not ok:
        return jsonify(payload), 400
    return jsonify({"ok": True, **payload})


@predictor_bp.route("/api/predict/leads-count", methods=["GET"])
def api_leads_count():
    from predictor import count_leads
    ensure_schema()
    return jsonify({"count": count_leads()})
