import logging, re
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pathlib import Path
from flask import Blueprint, current_app as app, jsonify, render_template, request, send_from_directory, Response
from sqlalchemy import or_
from database import db, Inspection, Defect, get_settings, set_setting, DEFAULT_SETTINGS
from services.inspection_service import run_inspection, CATEGORIES, MODES
from services.ai_explainer import assistant_reply, llm_status
from services.report_generator import build_pdf

bp = Blueprint("main", __name__)
log = logging.getLogger("inspector")
MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")


def ok(**kw):
    return jsonify({"ok": True, **kw})


def fail(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


def page(tpl, active, **kw):
    return render_template(tpl, active=active, settings=get_settings(), **kw)


# ---------------- pages ----------------
@bp.route("/")
def index():
    return render_template("index.html", active="", settings=get_settings())


@bp.route("/dashboard")
def dashboard():
    return page("dashboard.html", "dashboard")


@bp.route("/inspection")
def inspection():
    return page("inspection.html", "inspection", categories=CATEGORIES, samples=app.samples,
                models=app.manager.list(), modes=list(MODES))


@bp.route("/history")
def history():
    return page("history.html", "history", categories=CATEGORIES)


@bp.route("/analytics")
def analytics_page():
    return page("analytics.html", "analytics")


@bp.route("/models")
def models_page():
    return page("models.html", "models", models=app.manager.list(get_settings()["device"]))


@bp.route("/reports")
def reports_page():
    return page("reports.html", "reports")


@bp.route("/settings")
def settings_page():
    return page("settings.html", "settings", categories=CATEGORIES, models=app.manager.list(), llm=llm_status(app.config))


# ---------------- media ----------------
@bp.route("/media/<kind>/<name>")
def media(kind, name):
    folder = {"uploads": app.config["UPLOAD_DIR"], "processed": app.config["PROCESSED_DIR"]}.get(kind)
    if not folder or not re.fullmatch(r"[A-Za-z0-9_\-]+\.jpg", name):
        return fail("Not found", 404)
    return send_from_directory(folder, name, as_attachment=request.args.get("download") == "1")


# ---------------- helpers ----------------
def find(ident):
    row = db.session.get(Inspection, int(ident)) if str(ident).isdigit() else Inspection.query.filter_by(inspection_code=ident).first()
    return row


def validate_upload(data: bytes, filename: str):
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in app.config["ALLOWED_EXT"]:
        raise ValueError("Unsupported file type. Use JPG, JPEG or PNG.")
    limit = float(get_settings()["max_upload_mb"]) * 1024 * 1024
    if len(data) > limit:
        raise ValueError(f"File exceeds the {get_settings()['max_upload_mb']} MB upload limit.")
    if not data.startswith(MAGIC):
        raise ValueError("File content is not a valid JPEG/PNG image.")


# ---------------- API ----------------
@bp.route("/api/inspect", methods=["POST"])
def api_inspect():
    st = get_settings()
    category = request.form.get("category") or st["default_category"]
    model = request.form.get("model") or st["default_model"]
    mode = request.form.get("mode") or "standard"
    sample = request.form.get("sample")
    try:
        if sample:
            s = next((x for x in app.samples if x["key"] == sample), None)
            if not s:
                return fail("Unknown sample image", 404)
            data = (Path(app.config["SAMPLE_DIR"]) / f"{sample}.png").read_bytes()
            category = request.form.get("category") or s["category"]
        else:
            f = request.files.get("image")
            if not f or not f.filename:
                return fail("No image uploaded")
            data = f.read()
            validate_upload(data, f.filename)
        rec = run_inspection(app._get_current_object(), app.manager, data, category, model, mode)
    except ValueError as e:
        return fail(str(e))
    except RuntimeError as e:
        log.exception("Inference failed")
        return fail(f"Inference failed: {e}", 500)
    return ok(inspection=rec.to_dict())


def _filtered():
    a = request.args
    q = Inspection.query
    if a.get("q"):
        like = f"%{a['q']}%"
        q = q.filter(or_(Inspection.inspection_code.ilike(like), Inspection.category.ilike(like), Inspection.model_name.ilike(like)))
    for col, key in ((Inspection.category, "category"), (Inspection.status, "status"), (Inspection.severity, "severity")):
        if a.get(key):
            q = q.filter(col == a[key])
    try:
        if a.get("date_from"):
            q = q.filter(Inspection.created_at >= datetime.strptime(a["date_from"], "%Y-%m-%d"))
        if a.get("date_to"):
            q = q.filter(Inspection.created_at < datetime.strptime(a["date_to"], "%Y-%m-%d") + timedelta(days=1))
    except ValueError:
        raise ValueError("Dates must be YYYY-MM-DD")
    return q


@bp.route("/api/inspections")
def api_inspections():
    try:
        q = _filtered()
    except ValueError as e:
        return fail(str(e))
    order = {"score": Inspection.anomaly_score.desc(), "oldest": Inspection.created_at.asc()}.get(request.args.get("sort"), Inspection.created_at.desc())
    q = q.order_by(order, Inspection.id.desc())
    per = min(int(request.args.get("per_page", 25)), 200)
    pg = q.paginate(page=int(request.args.get("page", 1)), per_page=per, error_out=False)
    return ok(inspections=[i.to_dict(False) for i in pg.items], total=pg.total, pages=pg.pages, page=pg.page)


@bp.route("/api/inspections/<ident>", methods=["GET", "DELETE"])
def api_inspection(ident):
    rec = find(ident)
    if not rec:
        return fail("Inspection not found", 404)
    if request.method == "DELETE":
        for folder, name in ((app.config["UPLOAD_DIR"], rec.original_image), (app.config["PROCESSED_DIR"], rec.heatmap_image),
                             (app.config["PROCESSED_DIR"], rec.annotated_image)):
            try:
                (Path(folder) / name).unlink(missing_ok=True)
            except OSError:
                log.warning("Could not delete %s", name)
        db.session.delete(rec)
        db.session.commit()
        return ok(deleted=ident)
    return ok(inspection=rec.to_dict())


@bp.route("/api/analytics")
def api_analytics():
    try:
        q = _filtered()
    except ValueError as e:
        return fail(str(e))
    rows = q.order_by(Inspection.created_at).all()
    daily, weekly = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in rows:
        isfail = r.status != "PASS"
        d = r.created_at.strftime("%Y-%m-%d")
        w = r.created_at.strftime("%G-W%V")
        daily[d][0] += 1; daily[d][1] += isfail
        weekly[w][0] += 1; weekly[w][1] += isfail
    defects = [d for r in rows for d in r.defects]
    cat_def = Counter()
    for r in rows:
        cat_def[r.category] += r.defect_count
    n = len(rows)
    return ok(
        total=n, passed=sum(r.status == "PASS" for r in rows), failed=sum(r.status == "FAIL" for r in rows),
        review=sum(r.status == "REVIEW REQUIRED" for r in rows), defects=len(defects),
        avg_time=round(sum(r.processing_time or 0 for r in rows) / n, 3) if n else 0,
        avg_score=round(sum(r.anomaly_score or 0 for r in rows) / n, 3) if n else 0,
        daily=[{"date": k, "total": v[0], "flagged": v[1]} for k, v in sorted(daily.items())],
        weekly=[{"week": k, "total": v[0], "flagged": v[1]} for k, v in sorted(weekly.items())],
        defect_types=dict(Counter(d.defect_type for d in defects).most_common()),
        defects_by_category=dict(cat_def), category_counts=dict(Counter(r.category for r in rows)),
        severity=dict(Counter(r.severity for r in rows)), model_usage=dict(Counter(r.model_name for r in rows)),
    )


@bp.route("/api/models")
def api_models():
    return ok(models=app.manager.list(get_settings()["device"]))


@bp.route("/api/assistant", methods=["POST"])
def api_assistant():
    d = request.get_json(silent=True) or {}
    question = (d.get("question") or "").strip()[:500]
    if not question:
        return fail("Question is required")
    rec = find(d["inspection_id"]) if d.get("inspection_id") else Inspection.query.order_by(Inspection.created_at.desc()).first()
    prev = None
    if rec:
        p = Inspection.query.filter(Inspection.created_at < rec.created_at).order_by(Inspection.created_at.desc()).first()
        prev = p.to_dict() if p else None
    text, src = assistant_reply(question, rec.to_dict() if rec else None, prev, app.config)
    return ok(answer=text, source=src, inspection_code=rec.inspection_code if rec else None)


@bp.route("/api/reports/<ident>")
def api_report(ident):
    rec = find(ident)
    if not rec:
        return fail("Inspection not found", 404)
    pdf = build_pdf(rec.to_dict(), app.config["UPLOAD_DIR"], app.config["PROCESSED_DIR"])
    (Path(app.config["REPORT_DIR"]) / f"{rec.inspection_code}.pdf").write_bytes(pdf)
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename={rec.inspection_code}_report.pdf"})


@bp.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        return ok(settings=get_settings(), llm=llm_status(app.config))
    d = request.get_json(silent=True) or {}
    try:
        checks = {"anomaly_threshold": lambda v: 0.1 <= float(v) <= 0.95, "sensitivity": lambda v: 0.5 <= float(v) <= 2.5,
                  "default_category": lambda v: v in CATEGORIES, "default_model": lambda v: app.manager.usable(v),
                  "device": lambda v: v in ("auto", "cpu", "cuda"), "max_upload_mb": lambda v: 1 <= float(v) <= 25,
                  "theme": lambda v: v in ("dark", "light")}
        for k, v in d.items():
            if k not in DEFAULT_SETTINGS or k not in checks:
                return fail(f"Unknown setting '{k}'")
            if not checks[k](v):
                return fail(f"Invalid value for {k}")
        for k, v in d.items():
            set_setting(k, v)
        db.session.commit()
    except (ValueError, TypeError):
        return fail("Invalid settings payload")
    return ok(settings=get_settings())


@bp.route("/api/health")
def api_health():
    ms = app.manager.list()
    try:
        n = Inspection.query.count(); dbok = True
    except Exception:
        n, dbok = 0, False
    try:
        import torch
        torch_info = {"installed": True, "cuda": torch.cuda.is_available()}
    except Exception:
        torch_info = {"installed": False, "cuda": False}
    return ok(status="healthy" if dbok else "degraded", database=dbok, inspections=n, torch=torch_info,
              llm=llm_status(app.config), models_ready=[m["key"] for m in ms if m["state"] in ("available", "demo")],
              version="1.0.0")
