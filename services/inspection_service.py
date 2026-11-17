import json, logging, time, uuid
from pathlib import Path
import cv2
from database import db, Inspection, Defect, get_settings, ModelConfiguration
from services import image_processor as ip
from services.ai_explainer import explain

log = logging.getLogger("inspector")
CATEGORIES = ["metal", "fabric", "pcb", "wood", "bottle", "general"]
MODES = {"standard": 1.0, "high-sensitivity": 1.6, "anomaly-detection": 1.0, "defect-localization": 1.0}
SEV_RANK = ip.SEV_RANK


def run_inspection(app, manager, data: bytes, category, model_key, mode="standard", source="upload"):
    cfg = app.config
    st = get_settings()
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category '{category}'")
    if mode not in MODES:
        raise ValueError(f"Unknown inspection mode '{mode}'")
    if not manager.usable(model_key):
        raise ValueError(f"Model '{model_key}' is not available: {manager.get(model_key).status()['reason']}")
    stages, t0 = [], time.perf_counter()

    def mark(name, t):
        stages.append({"name": name, "ms": round((time.perf_counter() - t) * 1000, 1)})

    t = time.perf_counter()
    raw = ip.decode(data)
    oh, ow = raw.shape[:2]
    if min(oh, ow) < 32:
        raise ValueError("Image is too small (minimum 32x32 px)")
    img = ip.preprocess(raw)
    mark("Image preprocessing", t)

    det = manager.get(model_key)
    t = time.perf_counter()
    z, mode_label = det.anomaly_map(img, category, st["device"])
    mark("Feature extraction & anomaly analysis", t)

    t = time.perf_counter()
    thr, sens = float(st["anomaly_threshold"]), float(st["sensitivity"]) * MODES[mode]
    score, zs, tz = ip.score_from_map(z, sens, thr)
    mark("Scoring", t)

    t = time.perf_counter()
    status = "FAIL" if score >= thr else "REVIEW REQUIRED" if score >= 0.75 * thr else "PASS"
    defects = ip.localize(zs, img, category, tz) if status != "PASS" else []
    if status == "FAIL" and not defects:
        status = "REVIEW REQUIRED"      # evidence exists but could not be localised
    mark("Defect localization", t)

    t = time.perf_counter()
    code = "INS-" + time.strftime("%y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
    paths = {"original": f"{code}_original.jpg", "heatmap": f"{code}_heatmap.jpg", "annotated": f"{code}_annotated.jpg"}
    cv2.imwrite(str(Path(cfg["UPLOAD_DIR"]) / paths["original"]), img)
    cv2.imwrite(str(Path(cfg["PROCESSED_DIR"]) / paths["heatmap"]), ip.heatmap_overlay(img, zs, tz))
    cv2.imwrite(str(Path(cfg["PROCESSED_DIR"]) / paths["annotated"]), ip.annotate(img, defects))
    mark("Visualization", t)

    severity = "None"
    for d in defects:
        if SEV_RANK[d["severity"]] > SEV_RANK[severity]:
            severity = d["severity"]
    if status == "REVIEW REQUIRED" and severity == "None":
        severity = "Low"

    rec = Inspection(inspection_code=code, category=category, model_name=det.name, original_image=paths["original"],
                     heatmap_image=paths["heatmap"], annotated_image=paths["annotated"], anomaly_score=score,
                     defect_count=len(defects), severity=severity, status=status, inference_mode=mode_label,
                     inspection_mode=mode, width=img.shape[1], height=img.shape[0])
    for d in defects:
        rec.defects.append(Defect(**d))
    t = time.perf_counter()
    text, src = explain(_ctx(rec, defects), app.config)
    mark("Report generation", t)
    rec.explanation, rec.explanation_source = text, src
    rec.processing_time = time.perf_counter() - t0
    rec.stages = json.dumps(stages)
    db.session.add(rec)
    db.session.commit()
    log.info("Inspection %s %s score=%.3f defects=%d", code, status, score, len(defects))
    return rec


def _ctx(rec, defects):
    return {"inspection_code": rec.inspection_code, "category": rec.category, "model_name": rec.model_name,
            "anomaly_score": round(rec.anomaly_score, 3), "status": rec.status, "severity": rec.severity,
            "inference_mode": rec.inference_mode, "width": rec.width, "height": rec.height,
            "defects": [dict(d) for d in defects]}


def sync_model_configs(manager):
    for info in manager.list():
        row = ModelConfiguration.query.filter_by(model_name=info["key"]).first() or ModelConfiguration(model_name=info["key"])
        row.model_type, row.is_available = info["architecture"], info["state"] in ("available", "demo")
        row.configuration = json.dumps({"state": info["state"], "reason": info["reason"]})
        db.session.add(row)
    db.session.commit()
