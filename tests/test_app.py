import io, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import cv2, numpy as np, pytest
from app import create_app
from config import TestConfig
from database import db, Inspection


@pytest.fixture()
def client(tmp_path, monkeypatch):
    class C(TestConfig):
        UPLOAD_DIR = tmp_path / "u"; PROCESSED_DIR = tmp_path / "p"; REPORT_DIR = tmp_path / "r"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app = create_app(C)
    with app.app_context():
        yield app.test_client(), app


def sample_bytes(name):
    return open(os.path.join(os.path.dirname(__file__), "..", "static", "samples", name + ".png"), "rb").read()


def post(c, name="scratched_metal", **kw):
    data = {"image": (io.BytesIO(sample_bytes(name)), name + ".png"), "category": "metal", "model": "autoencoder", **kw}
    return c.post("/api/inspect", data=data, content_type="multipart/form-data")


def test_pages_load(client):
    c, _ = client
    for p in ["/", "/dashboard", "/inspection", "/history", "/analytics", "/models", "/reports", "/settings"]:
        assert c.get(p).status_code == 200, p


def test_health_and_models(client):
    c, _ = client
    assert c.get("/api/health").json["status"] == "healthy"
    m = {x["key"]: x for x in c.get("/api/models").json["models"]}
    assert m["classical"]["state"] == "demo" and m["efficientnet"]["state"] == "unavailable" and not m["efficientnet"]["loaded"]


def test_end_to_end(client):
    c, app = client
    r = post(c); assert r.status_code == 200, r.json
    ins = r.json["inspection"]
    assert ins["status"] in ("FAIL", "REVIEW REQUIRED") and ins["defect_count"] >= 1 and ins["explanation"]
    assert Inspection.query.count() == 1                              # persistence
    assert c.get("/api/inspections").json["total"] == 1                # history
    assert c.get(f"/api/inspections/{ins['id']}").json["inspection"]["inspection_code"] == ins["inspection_code"]
    a = c.get("/api/analytics").json; assert a["total"] == 1 and a["defects"] >= 1   # analytics
    for img in (ins["original_image"],):
        assert c.get(f"/media/uploads/{img}").status_code == 200
    assert c.get(f"/media/processed/{ins['heatmap_image']}").status_code == 200
    pdf = c.get(f"/api/reports/{ins['id']}"); assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    ans = c.post("/api/assistant", json={"question": "Which region is most suspicious?", "inspection_id": ins["id"]}).json
    assert ans["source"] == "local-template" and ans["answer"]       # missing API key -> fallback
    assert c.delete(f"/api/inspections/{ins['id']}").json["ok"] and c.get("/api/inspections").json["total"] == 0


def test_normal_sample_passes(client):
    c, _ = client
    assert post(c, "normal_metal").json["inspection"]["status"] == "PASS"


def test_invalid_uploads(client):
    c, _ = client
    r = c.post("/api/inspect", data={"image": (io.BytesIO(b"not an image"), "x.png")}, content_type="multipart/form-data")
    assert r.status_code == 400 and not r.json["ok"]
    r = c.post("/api/inspect", data={"image": (io.BytesIO(b"x"), "x.txt")}, content_type="multipart/form-data")
    assert r.status_code == 400
    assert c.post("/api/inspect", data={}, content_type="multipart/form-data").status_code == 400
    assert post(c, model="efficientnet").status_code == 400          # unavailable model refused
    assert c.get("/api/inspections/9999").status_code == 404


def test_sample_endpoint_and_settings(client):
    c, _ = client
    assert c.post("/api/inspect", data={"sample": "defective_wood", "category": "wood", "model": "autoencoder"}).json["inspection"]["defect_count"] >= 1
    assert c.post("/api/settings", json={"anomaly_threshold": "0.99"}).status_code == 400
    assert c.post("/api/settings", json={"anomaly_threshold": "0.3"}).json["settings"]["anomaly_threshold"] == "0.3"
