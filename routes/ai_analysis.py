from flask import Blueprint, request, jsonify
from routes.auth import login_required
from services.ai_service import analyze_log_with_ai, beautify_root_cause_action
from services.historical_search import search_similar_failures
from models.defect_report import DefectReport

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/api/ai/analyze-log", methods=["POST"])
@login_required
def analyze_log():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    sequence_log = data.get("sequence_log", "")
    buffer_log = data.get("buffer_log", "")
    log_content = data.get("log_content", "")
    failure = data.get("failure", "")
    defect_class = data.get("defect_class", "")
    station = data.get("station", "")
    bu = data.get("bu", "")
    keywords = data.get("keywords", "")
    exclude_id = data.get("exclude_id")  # ID of record being edited

    if not sequence_log and not buffer_log and not log_content and not failure:
        return jsonify({"error": "Please provide log content or failure information"}), 400

    # Combine logs for AI analysis
    if sequence_log or buffer_log:
        combined_log = f"=== SEQUENCE LOG ===\n{sequence_log}\n\n=== BUFFER LOG ===\n{buffer_log}"
    else:
        combined_log = log_content

    result = analyze_log_with_ai(
        combined_log, failure, defect_class, station, bu, keywords=keywords, exclude_id=exclude_id
    )
    return jsonify(result)


@ai_bp.route("/api/ai/beautify", methods=["POST"])
@login_required
def beautify():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    root_cause = data.get("root_cause", "").strip()
    action = data.get("action", "").strip()

    if not root_cause and not action:
        return jsonify({"error": "Please provide Root Cause or Action text to beautify"}), 400

    result = beautify_root_cause_action(root_cause, action)
    return jsonify(result)


@ai_bp.route("/api/ai/search-similar", methods=["POST"])
@login_required
def search_similar():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    failure = data.get("failure", "")
    station = data.get("station", "")
    bu = data.get("bu", "")
    exclude_id = data.get("exclude_id")

    if not failure:
        return jsonify({"error": "Failure information is required"}), 400

    results = search_similar_failures(failure, station=station, bu=bu, exclude_id=exclude_id)
    return jsonify({"success": True, "results": results})


@ai_bp.route("/api/ai/history-query", methods=["POST"])
@login_required
def history_query():
    """Query same BU + same Failure, return latest 3 records with Root Cause and Action."""
    from models import db
    from sqlalchemy import case, func

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    bu = data.get("bu", "").strip()
    failure = data.get("failure", "").strip()
    exclude_id = data.get("exclude_id")

    if not bu or not failure:
        return jsonify({"error": "BU and Failure are required for history query"}), 400

    # Use TRIM + case-insensitive comparison for robust matching
    # Search ALL records (including drafts) for history
    query = DefectReport.query.filter(
        func.lower(func.trim(DefectReport.bu)) == bu.lower(),
        func.lower(func.trim(DefectReport.failure)) == failure.lower(),
    )

    if exclude_id:
        query = query.filter(DefectReport.id != int(exclude_id))

    # Prioritize records with root_cause filled, then by most recent
    records = (
        query.order_by(case((DefectReport.root_cause.isnot(None), 0), else_=1), DefectReport.created_at.desc())
        .limit(3)
        .all()
    )

    results = []
    for r in records:
        results.append(
            {
                "id": r.id,
                "sn": r.sn or "",
                "station": r.station or "",
                "failure": r.failure or "",
                "defect_class": r.defect_class or "",
                "root_cause": r.root_cause or "",
                "action": r.action or "",
                "record_time": r.record_time.strftime("%Y-%m-%d %H:%M") if r.record_time else "",
            }
        )

    return jsonify({"success": True, "results": results})
