import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

DEFAULT_SETTINGS = {
    "anomaly_threshold": "0.50",   # score >= threshold -> FAIL
    "sensitivity": "1.0",          # multiplier applied to anomaly evidence
    "default_category": "metal",
    "default_model": "autoencoder",
    "device": "auto",              # auto | cpu | cuda
    "max_upload_mb": "10",
    "theme": "dark",
}


class Inspection(db.Model):
    __tablename__ = "inspection"
    id = db.Column(db.Integer, primary_key=True)
    inspection_code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    category = db.Column(db.String(32), nullable=False)
    model_name = db.Column(db.String(64), nullable=False)
    original_image = db.Column(db.String(256))
    heatmap_image = db.Column(db.String(256))
    annotated_image = db.Column(db.String(256))
    anomaly_score = db.Column(db.Float, default=0.0)
    defect_count = db.Column(db.Integer, default=0)
    severity = db.Column(db.String(16), default="None")
    status = db.Column(db.String(24), default="PASS")
    processing_time = db.Column(db.Float, default=0.0)
    inference_mode = db.Column(db.String(160))
    inspection_mode = db.Column(db.String(32), default="standard")
    explanation = db.Column(db.Text)
    explanation_source = db.Column(db.String(32))
    stages = db.Column(db.Text)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    defects = db.relationship("Defect", backref="inspection", cascade="all, delete-orphan", order_by="Defect.id")

    def to_dict(self, with_defects=True):
        d = {
            "id": self.id, "inspection_code": self.inspection_code, "category": self.category,
            "model_name": self.model_name, "original_image": self.original_image,
            "heatmap_image": self.heatmap_image, "annotated_image": self.annotated_image,
            "anomaly_score": round(self.anomaly_score or 0, 4), "defect_count": self.defect_count,
            "severity": self.severity, "status": self.status,
            "processing_time": round(self.processing_time or 0, 3), "inference_mode": self.inference_mode,
            "inspection_mode": self.inspection_mode, "explanation": self.explanation,
            "explanation_source": self.explanation_source, "width": self.width, "height": self.height,
            "stages": json.loads(self.stages) if self.stages else [],
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
        if with_defects:
            d["defects"] = [x.to_dict() for x in self.defects]
        return d


class Defect(db.Model):
    __tablename__ = "defect"
    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey("inspection.id"), nullable=False, index=True)
    defect_type = db.Column(db.String(64))
    severity = db.Column(db.String(16))
    confidence = db.Column(db.Float)      # relative anomaly strength 0-1 (heuristic, not a calibrated probability)
    x = db.Column(db.Integer)
    y = db.Column(db.Integer)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    description = db.Column(db.Text)

    def to_dict(self):
        return {"id": self.id, "defect_type": self.defect_type, "severity": self.severity,
                "confidence": round(self.confidence or 0, 3), "x": self.x, "y": self.y,
                "width": self.width, "height": self.height, "description": self.description}


class ModelConfiguration(db.Model):
    __tablename__ = "model_configuration"
    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(64), unique=True)
    model_type = db.Column(db.String(64))
    weights_path = db.Column(db.String(256))
    is_available = db.Column(db.Boolean, default=False)
    configuration = db.Column(db.Text)


class Setting(db.Model):
    __tablename__ = "setting"
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(256))


def get_settings():
    s = dict(DEFAULT_SETTINGS)
    for row in Setting.query.all():
        if row.key in s:
            s[row.key] = row.value
    return s


def set_setting(key, value):
    if key not in DEFAULT_SETTINGS:
        return
    row = db.session.get(Setting, key) or Setting(key=key)
    row.value = str(value)
    db.session.add(row)
