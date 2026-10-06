"""Application settings, read from environment variables with safe defaults for development."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = Path(os.getenv("VAULT_DATA_DIR", BASE_DIR / "data"))
STORAGE_DIR = DATA_DIR / "storage"          # encrypted blobs (disk backend only)
MASTER_KEY_FILE = DATA_DIR / "master.key"   # used only when VAULT_MASTER_KEY is not set

# "development" (local) or "production" (Render). Production refuses to start without real secrets.
ENVIRONMENT = os.getenv("VAULT_ENV", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"


def _normalize_database_url(url: str) -> str:
    """Render/Heroku give 'postgres://' or 'postgresql://'; SQLAlchemy needs the psycopg driver name."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalize_database_url(
    os.getenv("VAULT_DATABASE_URL") or os.getenv("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'vault.db'}"
)

# Where encrypted files live:
#   "disk"     -> data/storage/<id>.enc (local demo, lets you show the unreadable files)
#   "database" -> ciphertext column in the DB (required on hosts with an ephemeral filesystem, e.g. Render free)
STORAGE_BACKEND = os.getenv("VAULT_STORAGE_BACKEND", "database" if IS_PRODUCTION else "disk").lower()

# Comma-separated list of frontend origins allowed to call the API (e.g. https://boveda-ia.vercel.app)
CORS_ORIGINS = [origin.strip().rstrip("/") for origin in os.getenv("VAULT_CORS_ORIGINS", "").split(",") if origin.strip()]
# Optional regex, e.g. https://boveda-ia-.*\.vercel\.app to allow Vercel preview deployments
CORS_ORIGIN_REGEX = os.getenv("VAULT_CORS_ORIGIN_REGEX") or None

# Public URL of the API that the frontend should call ("" = same origin)
PUBLIC_API_URL = os.getenv("VAULT_PUBLIC_API_URL", "").rstrip("/")

# JWT
JWT_SECRET = os.getenv("VAULT_JWT_SECRET", "")  # generated on first run if empty (development only)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("VAULT_TOKEN_MINUTES", "60"))

# Uploads
MAX_UPLOAD_BYTES = int(os.getenv("VAULT_MAX_UPLOAD_MB", "10")) * 1024 * 1024
ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".pdf", ".docx"}

# Initial administrator (created only when the user table is empty)
DEFAULT_ADMIN_USERNAME = os.getenv("VAULT_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("VAULT_ADMIN_PASSWORD", "Admin123*")

# Brute-force protection
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def validate_production_settings() -> None:
    """On an ephemeral host, a generated key would be lost on restart and every document would become unreadable."""
    if not IS_PRODUCTION:
        return
    missing = [name for name in ("VAULT_MASTER_KEY", "VAULT_JWT_SECRET", "VAULT_ADMIN_PASSWORD") if not os.getenv(name)]
    if missing:
        raise RuntimeError("Faltan variables de entorno obligatorias en producción: " + ", ".join(missing))
    if DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("En producción configura DATABASE_URL con una base de datos PostgreSQL.")
    if STORAGE_BACKEND != "database":
        raise RuntimeError("En producción usa VAULT_STORAGE_BACKEND=database (el disco de Render es efímero).")
