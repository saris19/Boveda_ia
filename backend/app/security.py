"""Password hashing, JWT tokens and FastAPI dependencies for authentication and roles."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_jwt_secret: str | None = None


def get_jwt_secret() -> str:
    """Use VAULT_JWT_SECRET if set, otherwise persist a random secret next to the database."""
    global _jwt_secret
    if _jwt_secret:
        return _jwt_secret
    if config.JWT_SECRET:
        _jwt_secret = config.JWT_SECRET
        return _jwt_secret
    secret_file = config.DATA_DIR / "jwt.secret"
    if secret_file.exists():
        _jwt_secret = secret_file.read_text().strip()
    else:
        _jwt_secret = secrets.token_urlsafe(48)
        secret_file.write_text(_jwt_secret)
    return _jwt_secret


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def validate_password_strength(password: str) -> None:
    """Minimum policy: 8+ chars, upper, lower, digit and symbol."""
    rules = [
        (len(password) >= 8, "al menos 8 caracteres"),
        (any(c.isupper() for c in password), "una mayúscula"),
        (any(c.islower() for c in password), "una minúscula"),
        (any(c.isdigit() for c in password), "un número"),
        (any(not c.isalnum() for c in password), "un símbolo"),
    ]
    missing = [message for ok, message in rules if not ok]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe tener " + ", ".join(missing) + ".",
        )


def create_access_token(user: User) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.ACCESS_TOKEN_MINUTES)
    payload = {"sub": str(user.id), "role": user.role.value, "exp": expires_at}
    return jwt.encode(payload, get_jwt_secret(), algorithm=config.JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión inválida o expirada.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[config.JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise credentials_error
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_roles(*allowed_roles: Role):
    """Dependency factory: only lets through users whose role is in allowed_roles."""

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para esta acción.")
        return current_user

    return checker
