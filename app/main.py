"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from app import config
from app.ai.classifier import get_classifier
from app.crypto.vault_crypto import load_master_key
from app.database import Base, SessionLocal, engine
from app.models import Role, User
from app.routers import auth, documents, users
from app.security import get_jwt_secret, hash_password



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
    load_master_key()
    get_jwt_secret()
    get_classifier()  # trains the model once at startup
    create_default_admin()
    yield


app = FastAPI(
    title="Bóveda IA — Bodega de documentos cifrados",
    description="Almacenamiento cifrado (AES-256-GCM), control de acceso por roles y análisis con IA.",
    version="0.4.0",
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


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


@app.get("/config.js", include_in_schema=False)
def frontend_config():
    """When the backend serves the frontend itself, the API lives on the same origin."""
    return Response(f'window.VAULT_API_URL = "{config.PUBLIC_API_URL}";', media_type="application/javascript")


@app.get("/api/health", tags=["Sistema"], summary="Estado del servicio")
def health():
    return {"status": "ok", "version": app.version}
