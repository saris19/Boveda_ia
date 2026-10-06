"""User management (admin only) and audit-log queries."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AccessLog, Role, User
from app.schemas import AccessLogOut, UserCreate, UserOut, UserUpdate
from app.security import hash_password, require_roles, validate_password_strength
from app.services.audit_service import log_access

router = APIRouter(prefix="/api", tags=["Administración"])
admin_only = require_roles(Role.ADMIN)


@router.get("/users", response_model=list[UserOut], summary="Listar usuarios")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN, Role.EDITOR))):
    # Editors can see the user list to share documents.
    return db.scalars(select(User).order_by(User.username)).all()


@router.post("/users", response_model=UserOut, status_code=201, summary="Crear usuario")
def create_user(
    payload: UserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)
):
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese nombre de usuario ya existe.")
    validate_password_strength(payload.password)
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    log_access(db, request, "user_create", user=admin, detail=f"{user.username} ({user.role.value})")
    return user


@router.patch("/users/{user_id}", response_model=UserOut, summary="Cambiar rol o activar/desactivar")
def update_user(
    user_id: int, payload: UserUpdate, request: Request, db: Session = Depends(get_db), admin: User = Depends(admin_only)
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if user.id == admin.id and (payload.role not in (None, Role.ADMIN) or payload.is_active is False):
        raise HTTPException(status_code=400, detail="No puedes quitarte tu propio rol de administrador ni desactivarte.")
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    log_access(db, request, "user_update", user=admin, detail=f"{user.username}: rol={user.role.value}, activo={user.is_active}")
    return user


@router.get("/audit", response_model=list[AccessLogOut], summary="Bitácora de accesos")
def audit_log(
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
    limit: int = Query(100, le=1000),
    only_failed: bool = False,
):
    query = select(AccessLog).order_by(AccessLog.timestamp.desc()).limit(limit)
    if only_failed:
        query = query.where(AccessLog.success.is_(False))
    return db.scalars(query).all()
