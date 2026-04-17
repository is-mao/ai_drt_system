from models import db
from models.defect_report import DefectReport
from flask import Blueprint, request, jsonify, render_template
from routes.auth import login_required
from sqlalchemy import func
from config import Config
from datetime import datetime, timedelta
from services.db_routing import get_user_db

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="")


@dashboard_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard_page():
    return render_template("dashboard.html", bu_options=Config.BU_OPTIONS)


@dashboard_bp.route("/api/dashboard/summary", methods=["GET"])
@login_required
def dashboard_summary():
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    udb = get_user_db()
    query = udb.session.query(DefectReport).filter(
        db.or_(DefectReport.status == "complete", DefectReport.status.is_(None))
    )

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

    total_count = query.count()
    # Single GROUP BY query instead of N+1
    bu_rows = query.with_entities(DefectReport.bu, func.count(DefectReport.id)).group_by(DefectReport.bu).all()
    bu_counts = {b: 0 for b in Config.BU_OPTIONS}
    bu_counts.update({r[0]: r[1] for r in bu_rows if r[0] in bu_counts})

    # This week count: apply same filters as the main query
    today = datetime.now().date()
    jan1 = today.replace(month=1, day=1)
    current_week = (today.timetuple().tm_yday - 1) // 7 + 1
    week_start = jan1 + timedelta(days=(current_week - 1) * 7)
    week_end = jan1 + timedelta(days=current_week * 7 - 1)
    dec31 = today.replace(month=12, day=31)
    if week_end > dec31:
        week_end = dec31
    this_week_query = query.filter(
        DefectReport.record_time >= datetime.combine(week_start, datetime.min.time()),
        DefectReport.record_time
        <= datetime.combine(week_end, datetime.min.time()).replace(hour=23, minute=59, second=59),
    )
    this_week_count = this_week_query.count()

    result = {
        "total_count": total_count,
        "this_week_count": this_week_count,
        "bu_counts": bu_counts,
    }
    return jsonify(result)


@dashboard_bp.route("/api/dashboard/weekly-trend", methods=["GET"])
@login_required
def weekly_trend():
    bu = request.args.get("bu")
    year = request.args.get("year", datetime.now().year, type=int)

    today = datetime.now().date()

    # Week calculation: Jan 1 = W01, each 7 days = 1 week
    jan1 = today.replace(year=year, month=1, day=1)
    # Calculate total weeks in this year
    dec31 = today.replace(year=year, month=12, day=31)
    total_weeks = (dec31.timetuple().tm_yday - 1) // 7 + 1

    # Only show up to current week if viewing current year
    if year == today.year:
        current_week = (today.timetuple().tm_yday - 1) // 7 + 1
        show_weeks = current_week
    else:
        show_weeks = total_weeks

    labels = []
    bu_datasets = {b: [] for b in Config.BU_OPTIONS}

    # Build week boundaries
    week_ranges = []
    for w in range(1, show_weeks + 1):
        week_start = jan1 + timedelta(days=(w - 1) * 7)
        week_end_date = jan1 + timedelta(days=w * 7 - 1)
        if week_end_date > dec31:
            week_end_date = dec31
        year_short = year % 100
        labels.append(f"{year_short}WK{w:02d}")
        week_ranges.append((w, week_start, week_end_date))

    # Single query: fetch all counts grouped by week and BU
    udb = get_user_db()
    if week_ranges:
        dt_year_start = datetime.combine(week_ranges[0][1], datetime.min.time())
        dt_year_end = datetime.combine(week_ranges[-1][2], datetime.min.time()).replace(hour=23, minute=59, second=59)

        base_query = udb.session.query(DefectReport).filter(
            DefectReport.record_time >= dt_year_start,
            DefectReport.record_time <= dt_year_end,
            db.or_(DefectReport.status == "complete", DefectReport.status.is_(None)),
        )
        if bu and bu.upper() in Config.BU_OPTIONS:
            base_query = base_query.filter(DefectReport.bu == bu.upper())

        all_records = base_query.with_entities(DefectReport.record_time, DefectReport.bu).all()

        # Distribute records into week buckets
        week_bu_counts = {}  # (week_num, bu) -> count
        for rec_time, rec_bu in all_records:
            if rec_time is None or rec_bu is None:
                continue
            rec_date = rec_time.date() if hasattr(rec_time, "date") else rec_time
            day_of_year = rec_date.timetuple().tm_yday
            w_num = (day_of_year - 1) // 7 + 1
            if 1 <= w_num <= show_weeks:
                key = (w_num, rec_bu)
                week_bu_counts[key] = week_bu_counts.get(key, 0) + 1

        for w, _, _ in week_ranges:
            for b in Config.BU_OPTIONS:
                bu_datasets[b].append(week_bu_counts.get((w, b), 0))

    datasets = []
    for b in Config.BU_OPTIONS:
        if not bu or bu.upper() == b:
            datasets.append({"label": b, "data": bu_datasets[b]})

    return jsonify({"labels": labels, "datasets": datasets})


@dashboard_bp.route("/api/dashboard/defect-class-distribution", methods=["GET"])
@login_required
def defect_class_distribution():
    bu = request.args.get("bu")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    udb = get_user_db()
    query = udb.session.query(DefectReport.defect_class, func.count(DefectReport.id).label("count"))

    if bu and bu.upper() in Config.BU_OPTIONS:
        query = query.filter(DefectReport.bu == bu.upper())

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

    query = query.filter(DefectReport.defect_class.isnot(None))
    query = query.filter(db.or_(DefectReport.status == "complete", DefectReport.status.is_(None)))
    results = query.group_by(DefectReport.defect_class).order_by(func.count(DefectReport.id).desc()).all()

    labels = [r[0] for r in results]
    data = [r[1] for r in results]

    return jsonify({"labels": labels, "data": data})


@dashboard_bp.route("/api/dashboard/top-stations", methods=["GET"])
@login_required
def top_stations():
    bu = request.args.get("bu")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    udb = get_user_db()
    query = udb.session.query(DefectReport.station, func.count(DefectReport.id).label("count"))

    if bu and bu.upper() in Config.BU_OPTIONS:
        query = query.filter(DefectReport.bu == bu.upper())

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

    query = query.filter(
        DefectReport.station.isnot(None),
        DefectReport.station != "",
        db.or_(DefectReport.status == "complete", DefectReport.status.is_(None)),
    )
    results = query.group_by(DefectReport.station).order_by(func.count(DefectReport.id).desc()).limit(10).all()

    labels = [r[0] for r in results]
    data = [r[1] for r in results]

    return jsonify({"labels": labels, "data": data})


@dashboard_bp.route("/api/dashboard/top-servers", methods=["GET"])
@login_required
def top_servers():
    bu = request.args.get("bu")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    udb = get_user_db()
    query = udb.session.query(DefectReport.server, func.count(DefectReport.id).label("count"))

    if bu and bu.upper() in Config.BU_OPTIONS:
        query = query.filter(DefectReport.bu == bu.upper())

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

    query = query.filter(
        DefectReport.server.isnot(None),
        DefectReport.server != "",
        db.or_(DefectReport.status == "complete", DefectReport.status.is_(None)),
    )
    results = query.group_by(DefectReport.server).order_by(func.count(DefectReport.id).desc()).limit(10).all()

    labels = [r[0] for r in results]
    data = [r[1] for r in results]

    return jsonify({"labels": labels, "data": data})


@dashboard_bp.route("/api/dashboard/top-pcapn", methods=["GET"])
@login_required
def top_pcapn():
    bu = request.args.get("bu")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    udb = get_user_db()
    query = udb.session.query(DefectReport.pcap_n, func.count(DefectReport.id).label("count"))

    if bu and bu.upper() in Config.BU_OPTIONS:
        query = query.filter(DefectReport.bu == bu.upper())

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

    query = query.filter(
        DefectReport.pcap_n.isnot(None),
        DefectReport.pcap_n != "",
        db.or_(DefectReport.status == "complete", DefectReport.status.is_(None)),
    )
    results = query.group_by(DefectReport.pcap_n).order_by(func.count(DefectReport.id).desc()).limit(10).all()

    labels = [r[0] for r in results]
    data = [r[1] for r in results]

    return jsonify({"labels": labels, "data": data})


@dashboard_bp.route("/api/dashboard/top-failures", methods=["GET"])
@login_required
def top_failures():
    bu = request.args.get("bu")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    udb = get_user_db()
    query = udb.session.query(DefectReport.failure, func.count(DefectReport.id).label("count"))

    if bu and bu.upper() in Config.BU_OPTIONS:
        query = query.filter(DefectReport.bu == bu.upper())

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

    query = query.filter(
        DefectReport.failure.isnot(None),
        DefectReport.failure != "",
        db.or_(DefectReport.status == "complete", DefectReport.status.is_(None)),
    )
    results = query.group_by(DefectReport.failure).order_by(func.count(DefectReport.id).desc()).limit(10).all()

    labels = [r[0] for r in results]
    data = [r[1] for r in results]

    return jsonify({"labels": labels, "data": data})
