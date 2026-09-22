"""Application configuration — single source of truth.

Local dev: copy .env.example to .env and fill in what you need.
Production (Render): set the same variables in the environment dashboard.
Secrets are never read from anywhere else and never committed.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PHOTO_DIR = DATA_DIR / "photos"  # local-dev fallback storage only


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


class Settings:
    # --- Environment ---
    ENVIRONMENT: str = _env("ENVIRONMENT", "development")

    # --- App ---
    APP_NAME: str = "Riparia"
    PUBLIC_BASE_URL: str = _env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    _raw_origins = _env("ALLOWED_ORIGINS", PUBLIC_BASE_URL)
    ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

    # --- Database ---
    DATABASE_URL: str = _env(
        "DATABASE_URL", f"sqlite:///{(DATA_DIR / 'riparia.db').as_posix()}"
    )
    # Render/Heroku-style URLs need the psycopg driver spelled out.
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

    # --- AI ---
    GEMINI_API_KEY: str = _env("GEMINI_API_KEY")
    # 'gemini-flash-latest' alias always resolves to a live flash-tier model.
    GEMINI_MODEL: str = _env("GEMINI_MODEL", "gemini-flash-latest")

    # --- FHIR ---
    FHIR_BASE_URL: str = _env("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4").rstrip("/")

    # --- Object storage (Cloudflare R2, S3-compatible) ---
    R2_ACCOUNT_ID: str = _env("R2_ACCOUNT_ID")
    R2_ACCESS_KEY_ID: str = _env("R2_ACCESS_KEY_ID")
    R2_SECRET_ACCESS_KEY: str = _env("R2_SECRET_ACCESS_KEY")
    R2_BUCKET: str = _env("R2_BUCKET")
    R2_PUBLIC_BASE: str = _env("R2_PUBLIC_URL", "").rstrip("/")  # signed-URL delivery

    # --- Auth / sessions ---
    _DEV_SECRET = "dev-only-insecure-secret-change-me"
    SESSION_SECRET: str = _env(
        "SESSION_SECRET", _DEV_SECRET if ENVIRONMENT == "development" else ""
    )
    REVIEWER_USERNAME: str = _env("REVIEWER_USERNAME", "reviewer")
    REVIEWER_PASSWORD_HASH: str = _env(
        "REVIEWER_PASSWORD_HASH",
        # bcrypt hash of "reviewer-dev-password" — development fallback only
        "$2b$12$VsOxqi1z4Ju2kXGiLrfFh.mOik7ZXH/fiSTSwODSDz.4EcNlFfIEq",
    )
    # --- Uploads ---
    MAX_PHOTO_BYTES: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_PHOTO_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp", "image/gif"}

    # --- Rate limits (slowapi) ---
    RATE_LIMIT_SUBMIT: str = _env("RATE_LIMIT_SUBMIT", "10/minute")
    RATE_LIMIT_AUTH: str = _env("RATE_LIMIT_AUTH", "5/minute")
    RATE_LIMIT_DEFAULT: str = _env("RATE_LIMIT_DEFAULT", "120/minute")


settings = Settings()

if settings.ENVIRONMENT == "production":
    problems = []
    if not settings.SESSION_SECRET or settings.SESSION_SECRET.startswith("dev-only"):
        problems.append("SESSION_SECRET must be set to a long random value in production")
    if settings.DATABASE_URL.startswith("sqlite"):
        problems.append("DATABASE_URL must point at PostgreSQL in production")
    if problems:
        raise RuntimeError(
            "Refusing to start in production with insecure settings: " + "; ".join(problems)
        )

PHOTO_DIR.mkdir(parents=True, exist_ok=True)
