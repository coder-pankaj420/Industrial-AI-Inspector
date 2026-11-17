import argparse, os
from app import create_app
from database import db, Inspection


def seed(app):
    """Run the real pipeline on the bundled samples so dashboards are not empty."""
    from services.inspection_service import run_inspection
    with app.app_context():
        if Inspection.query.count():
            print("Database already has inspections - skipping seed.")
            return
        for s in app.samples:
            data = open(os.path.join(app.config["SAMPLE_DIR"], s["key"] + ".png"), "rb").read()
            r = run_inspection(app, app.manager, data, s["category"], "autoencoder")
            print(f"  seeded {r.inspection_code}  {s['key']:18s} {r.status}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Industrial AI Inspector")
    ap.add_argument("--init-db", action="store_true", help="create tables, generate samples, seed sample inspections, then exit")
    ap.add_argument("--no-seed", action="store_true", help="with --init-db: do not create sample inspection records")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    a = ap.parse_args()
    app = create_app()
    if a.init_db:
        print("Database initialised.")
        if not a.no_seed:
            seed(app)
    else:
        app.run(host=a.host, port=a.port, debug=os.getenv("FLASK_DEBUG") == "1")
