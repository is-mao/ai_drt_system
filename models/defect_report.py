from models import db
from datetime import datetime


class DefectReport(db.Model):
    __tablename__ = "defect_reports"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bu = db.Column(db.String(10), nullable=False, index=True)
    week_number = db.Column(db.String(20))
    pcap_n = db.Column(db.String(100))
    station = db.Column(db.String(100), index=True)
    server = db.Column(db.String(100))
    sn = db.Column(db.String(100), index=True)
    record_time = db.Column(db.DateTime, index=True)
    failure = db.Column(db.Text)
    defect_class = db.Column(db.String(50), index=True)
    defect_value = db.Column(db.String(255))
    root_cause = db.Column(db.Text)
    action = db.Column(db.Text)
    pn = db.Column(db.String(100))
    component_sn = db.Column(db.String(100))
    log_content = db.Column(db.Text)
    sequence_log = db.Column(db.Text)
    buffer_log = db.Column(db.Text)
    ai_root_cause = db.Column(db.Text)
    # status: 'draft' = imported from Cesium (incomplete), 'complete' = ready for defect list
    status = db.Column(db.String(20), default="complete", index=True)
    created_by = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self, include_log=False):
        data = {
            "id": self.id,
            "bu": self.bu,
            "week_number": self.week_number,
            "pcap_n": self.pcap_n,
            "station": self.station,
            "server": self.server,
            "sn": self.sn,
            "record_time": self.record_time.strftime("%Y-%m-%d %H:%M:%S") if self.record_time else None,
            "failure": self.failure,
            "defect_class": self.defect_class,
            "defect_value": self.defect_value,
            "root_cause": self.root_cause,
            "action": self.action,
            "pn": self.pn,
            "component_sn": self.component_sn,
            "ai_root_cause": self.ai_root_cause,
            "status": self.status or "complete",
            "created_by": self.created_by,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }
        if include_log:
            data["log_content"] = self.log_content
            data["sequence_log"] = self.sequence_log
            data["buffer_log"] = self.buffer_log
        return data
