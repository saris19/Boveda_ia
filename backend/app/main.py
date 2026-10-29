"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app import config
from app.crypto.vault_crypto import load_master_key
from app.database import Base, SessionLocal, engine
from app.migrations import run_migrations
from app.models import Role, User
from app.routers import admin, alerts, auth, documents, search, stats, trash, users
from app.routers.trash import purge_expired
from app.security import get_jwt_secret, hash_password
from app.services.alert_service import train_model
from app.services.feedback_service import retrain_from_feedback



def create_default_admin() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User).limit(1)) is None:
            db.add(
                User(
                    username=config.DEFAULT_ADMIN_USERNAME,
                    full_name="Administrador",
                    password_hash=hash_password(config.DEFAULT_ADMIN_PASSWORD),
                    role=Role.ADMIN,
                )
            )
            db.commit()
            shown_password = "(VAULT_ADMIN_PASSWORD)" if config.IS_PRODUCTION else config.DEFAULT_ADMIN_PASSWORD
            print(f"[Bóveda] Usuario administrador creado: {config.DEFAULT_ADMIN_USERNAME} / {shown_password}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.validate_production_settings()
    config.ensure_dirs()
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    load_master_key()
    get_jwt_secret()
    retrain_from_feedback()  # classifier: seed corpus + stored human corrections
    create_default_admin()
    with SessionLocal() as db:
        purge_expired(db)    # recycle bin retention
        train_model(db)      # suspicious-access model: synthetic baseline + real access log
    yield


app = FastAPI(
    title="Bóveda IA — Bodega de documentos cifrados",
    description="Almacenamiento cifrado (AES-256-GCM), control de acceso por roles y sensibilidad, búsqueda en contenido cifrado y detección de accesos sospechosos con IA.",
    version="1.0.0",
    lifespan=lifespan,
)

if config.CORS_ORIGINS or config.CORS_ORIGIN_REGEX:
    # Bearer tokens travel in the Authorization header (no cookies), so credentials are not needed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_origin_regex=config.CORS_ORIGIN_REGEX,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(stats.router)
app.include_router(trash.router)
app.include_router(alerts.router)
app.include_router(admin.router)


@app.get("/", include_in_schema=False)
def root():
    """The web interface lives in the separate frontend (React). This API only serves JSON."""
    return {"service": "Bóveda IA API", "version": app.version, "docs": "/docs", "health": "/api/health"}


@app.get("/api/health", tags=["Sistema"], summary="Estado del servicio")
def health():
    return {"status": "ok", "version": app.version}
