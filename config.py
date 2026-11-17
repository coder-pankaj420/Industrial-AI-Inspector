import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:  # python-dotenv is optional
    env = BASE_DIR / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///" + str(BASE_DIR / "instance" / "inspector.db"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_DIR = BASE_DIR / "uploads"
    PROCESSED_DIR = BASE_DIR / "processed"
    REPORT_DIR = BASE_DIR / "reports"
    SAMPLE_DIR = BASE_DIR / "static" / "samples"
    DATASET_DIR = BASE_DIR / "datasets"
    ALLOWED_EXT = {"jpg", "jpeg", "png"}
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024          # hard ceiling; runtime limit comes from Settings
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
