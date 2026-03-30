from flask import Blueprint, request, jsonify, render_template, session
from datetime import datetime
from math import ceil
from models import db
from models.defect_report import DefectReport
from routes.auth import login_required
from config import Config

defects_bp = Blueprint("defects", __name__, url_prefix="")

DEFECT_CLASSES = Config.DEFECT_CLASSES
DEFECT_VALUES = Config.DEFECT_VALUES
DEFECT_CLASS_VALUE_MAP = Config.DEFECT_CLASS_VALUE_MAP
BU_OPTIONS = Config.BU_OPTIONS


# ---------------------------------------------------------------------------
# Page routes (render templates)
# ---------------------------------------------------------------------------


@defects_bp.route("/defects")
@login_required
def defect_list():
    return render_template(
        "defect_list.html",
        defect_classes=DEFECT_CLASSES,
        defect_values=DEFECT_VALUES,
        bu_options=BU_OPTIONS,
    )


@defects_bp.route("/defects/new")
@login_required
def defect_new():
    return render_template(
        "defect_form.html",
        mode="create",
        record=None,
        defect_classes=DEFECT_CLASSES,
        defect_values=DEFECT_VALUES,
        bu_options=BU_OPTIONS,
    )


@defects_bp.route("/defects/<int:id>/edit")
@login_required
def defect_edit(id):
    record = DefectReport.query.get_or_404(id)
    return render_template(
        "defect_form.html",
        mode="edit",
        record=record.to_dict(include_log=True),
        defect_classes=DEFECT_CLASSES,
        defect_values=DEFECT_VALUES,
        bu_options=BU_OPTIONS,
    )


@defects_bp.route("/defects/<int:id>")
@login_required
def defect_detail(id):
    record = DefectReport.query.get_or_404(id)
    return render_template(
        "defect_detail.html",
        record=record.to_dict(include_log=True),
        defect_classes=DEFECT_CLASSES,
        bu_options=BU_OPTIONS,
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@defects_bp.route("/api/defect-options")
@login_required
def defect_options():
    """Return the class → value → definition mapping as JSON."""
    return jsonify(DEFECT_CLASS_VALUE_MAP)


@defects_bp.route("/api/defects", methods=["GET"])
@login_required
def api_defect_list():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    bu = request.args.get("bu", "").strip()
    defect_class = request.args.get("defect_class", "").strip()
    defect_value = request.args.get("defect_value", "").strip()
    station = request.args.get("station", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    search = request.args.get("search", "").strip()
    sort_by = request.args.get("sort_by", "record_time").strip()
    sort_dir = request.args.get("sort_dir", "desc").strip()

    query = DefectReport.query.filter(db.or_(DefectReport.status == "complete", DefectReport.status.is_(None)))

    # Apply filters
    if bu:
        query = query.filter(DefectReport.bu == bu)
    if defect_class:
        query = query.filter(DefectReport.defect_class == defect_class)
    if defect_value:
        query = query.filter(DefectReport.defect_value == defect_value)
    if station:
        query = query.filter(DefectReport.station.ilike(f"%{station}%"))
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(DefectReport.record_time >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d")
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            query = query.filter(DefectReport.record_time <= dt_to)
        except ValueError:
            pass
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                DefectReport.sn.ilike(search_pattern),
                DefectReport.failure.ilike(search_pattern),
                DefectReport.root_cause.ilike(search_pattern),
                DefectReport.pn.ilike(search_pattern),
                DefectReport.pcap_n.ilike(search_pattern),
                DefectReport.server.ilike(search_pattern),
            )
        )

    # Sorting
    allowed_sort_columns = {
        "id",
        "bu",
        "week_number",
        "pcap_n",
        "station",
        "server",
        "sn",
        "record_time",
        "failure",
        "defect_class",
        "defect_value",
        "created_at",
        "updated_at",
    }
    if sort_by not in allowed_sort_columns:
        sort_by = "record_time"
    sort_col = getattr(DefectReport, sort_by)
    if sort_dir == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = query.count()
    total_pages = ceil(total / per_page) if per_page else 1
    records = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        {
            "data": [r.to_dict(include_log=False) for r in records],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }
    )


@defects_bp.route("/api/defects/<int:id>", methods=["GET"])
@login_required
def api_defect_get(id):
    record = DefectReport.query.get_or_404(id)
    return jsonify(record.to_dict(include_log=True))


@defects_bp.route("/api/defects", methods=["POST"])
@login_required
def api_defect_create():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    record = DefectReport(
        bu=data.get("bu", ""),
        week_number=data.get("week_number", ""),
        pcap_n=data.get("pcap_n", ""),
        station=data.get("station", ""),
        server=data.get("server", ""),
        sn=data.get("sn", ""),
        record_time=_parse_datetime(data.get("record_time")),
        failure=data.get("failure", ""),
        defect_class=data.get("defect_class", ""),
        defect_value=data.get("defect_value", ""),
        root_cause=data.get("root_cause", ""),
        action=data.get("action", ""),
        pn=data.get("pn", ""),
        component_sn=data.get("component_sn", ""),
        log_content=data.get("log_content", ""),
        sequence_log=data.get("sequence_log", ""),
        buffer_log=data.get("buffer_log", ""),
        ai_root_cause=data.get("ai_root_cause", ""),
        created_by=session.get("username", ""),
    )

    db.session.add(record)
    db.session.commit()

    return jsonify({"success": True, "id": record.id, "data": record.to_dict(include_log=True)}), 201


@defects_bp.route("/api/defects/<int:id>", methods=["PUT"])
@login_required
def api_defect_update(id):
    record = DefectReport.query.get_or_404(id)
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    updatable_fields = [
        "bu",
        "week_number",
        "pcap_n",
        "station",
        "server",
        "sn",
        "failure",
        "defect_class",
        "defect_value",
        "root_cause",
        "action",
        "pn",
        "component_sn",
        "log_content",
        "sequence_log",
        "buffer_log",
        "ai_root_cause",
    ]
    for field in updatable_fields:
        if field in data:
            setattr(record, field, data[field])

    if "record_time" in data:
        record.record_time = _parse_datetime(data["record_time"])

    # If record was draft, validate required fields and promote to complete
    if record.status == "draft":
        missing = []
        if not record.bu:
            missing.append("BU")
        if not record.sn:
            missing.append("SN")
        if not record.station:
            missing.append("Station")
        if not record.server:
            missing.append("Server")
        if not record.failure:
            missing.append("Failure")
        if not record.defect_class:
            missing.append("Defect Class")
        if not record.defect_value:
            missing.append("Defect Value")
        if not record.pcap_n:
            missing.append("PCAP/N")
        if not record.week_number:
            missing.append("Week#")
        if missing:
            return (
                jsonify({"success": False, "error": "Missing required fields to complete: " + ", ".join(missing)}),
                400,
            )
        record.status = "complete"

    db.session.commit()

    return jsonify({"success": True, "data": record.to_dict(include_log=True)})


@defects_bp.route("/api/defects/<int:id>", methods=["DELETE"])
@login_required
def api_defect_delete(id):
    record = DefectReport.query.get_or_404(id)
    db.session.delete(record)
    db.session.commit()
    return jsonify({"success": True, "message": f"Record #{id} deleted"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_datetime(value):
    """Parse a datetime string from the form (datetime-local or standard)."""
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
