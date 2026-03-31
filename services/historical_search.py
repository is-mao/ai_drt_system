from models import db
from models.defect_report import DefectReport


def search_similar_failures(failure, station=None, bu=None, exclude_id=None, limit=5):
    """Search historical records with similar failure patterns using FULLTEXT search."""
    results = []

    if not failure:
        return results

    try:
        # Try FULLTEXT search first
        query = DefectReport.query.filter(DefectReport.root_cause.isnot(None), DefectReport.root_cause != "")

        if bu:
            query = query.filter(DefectReport.bu == bu)

        # Exclude the record currently being edited
        if exclude_id:
            query = query.filter(DefectReport.id != exclude_id)

        # Use LIKE for pattern matching (works without FULLTEXT index on all DB engines)
        keywords = failure.split("_")
        for keyword in keywords[:3]:  # Use first 3 keywords
            if len(keyword) > 2:
                query = query.filter(DefectReport.failure.like(f"%{keyword}%"))

        if station:
            # Prioritize same station
            station_results = (
                query.filter(DefectReport.station == station)
                .order_by(DefectReport.record_time.desc())
                .limit(limit)
                .all()
            )
            results.extend(station_results)

        if len(results) < limit:
            remaining = limit - len(results)
            existing_ids = [r.id for r in results]
            more_results = (
                query.filter(DefectReport.id.notin_(existing_ids) if existing_ids else True)
                .order_by(DefectReport.record_time.desc())
                .limit(remaining)
                .all()
            )
            results.extend(more_results)

    except Exception:
        # Fallback: simple LIKE search
        query = DefectReport.query.filter(
            DefectReport.failure.like(f"%{failure[:50]}%"),
            DefectReport.root_cause.isnot(None),
            DefectReport.root_cause != "",
        )
        if bu:
            query = query.filter(DefectReport.bu == bu)
        results = query.order_by(DefectReport.record_time.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "failure": r.failure,
            "defect_class": r.defect_class,
            "defect_value": r.defect_value,
            "root_cause": r.root_cause,
            "action": r.action,
            "station": r.station,
            "bu": r.bu,
            "record_time": r.record_time.strftime("%Y-%m-%d %H:%M:%S") if r.record_time else None,
        }
        for r in results
    ]
