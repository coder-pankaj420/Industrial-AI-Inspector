import logging
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from config import Config
from database import db
from models.model_manager import ModelManager
from services.sample_data import ensure_samples

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    for k in ("UPLOAD_DIR", "PROCESSED_DIR", "REPORT_DIR", "SAMPLE_DIR", "DATASET_DIR"):
        Path(app.config[k]).mkdir(parents=True, exist_ok=True)
    Path(app.root_path, "instance").mkdir(exist_ok=True)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    db.init_app(app)
    app.manager = ModelManager(app.config["DATASET_DIR"], Path(app.root_path, "instance"))
    app.samples = ensure_samples(app.config["SAMPLE_DIR"], app.config["DATASET_DIR"])

    from routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        from services.inspection_service import sync_model_configs
        sync_model_configs(app.manager)

    @app.errorhandler(Exception)
    def on_error(e):
        from werkzeug.exceptions import HTTPException
        code = e.code if isinstance(e, HTTPException) else 500
        if code == 500:
            logging.getLogger("inspector").exception("Unhandled error")
        msg = e.description if isinstance(e, HTTPException) else "Internal server error"
        if code == 413:
            msg = "File too large"
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": msg}), code
        return render_template("error.html", code=code, message=msg, active=""), code

    return app
