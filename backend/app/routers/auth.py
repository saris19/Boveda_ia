"""Login endpoint with brute-force lockout and audit logging."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import User
from app.schemas import TokenResponse, UserOut
from app.security import create_access_token, get_current_user, verify_password
from app.services.alert_service import ip_login_blocked
from app.services.audit_service import log_access

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


def _as_aware(value: datetime) -> datetime:
    # SQLite returns naive datetimes; treat them as UTC.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.post("/login", response_model=TokenResponse, summary="Iniciar sesión")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos.")
    user = db.scalar(select(User).where(User.username == form.username))
    now = datetime.now(timezone.utc)

    client_ip = request.client.host if request.client else ""
    if ip_login_blocked(db, client_ip):
        log_access(db, request, "login", username=form.username, success=False, detail="IP bloqueada temporalmente")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos desde tu red. Intenta de nuevo en 15 minutos.",
        )

    if user is None:
        log_access(db, request, "login", username=form.username, success=False, detail="usuario inexistente")
        raise invalid

    if user.locked_until and _as_aware(user.locked_until) > now:
        log_access(db, request, "login", user=user, success=False, detail="cuenta bloqueada")
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Cuenta bloqueada por intentos fallidos. Intenta de nuevo en {config.LOCKOUT_MINUTES} minutos.",
        )

    if not user.is_active or not verify_password(form.password, user.password_hash):
        user.failed_logins += 1
        detail = f"contraseña incorrecta ({user.failed_logins}/{config.MAX_FAILED_LOGINS})"
        if user.failed_logins >= config.MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=config.LOCKOUT_MINUTES)
            user.failed_logins = 0
            detail = "cuenta bloqueada por fuerza bruta"
        db.commit()
        log_access(db, request, "login", user=user, success=False, detail=detail)
        raise invalid

    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    log_access(db, request, "login", user=user)
    return TokenResponse(access_token=create_access_token(user), role=user.role, username=user.username)


@router.get("/me", response_model=UserOut, summary="Usuario actual")
def me(current_user: User = Depends(get_current_user)):
    return current_user
