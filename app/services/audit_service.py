"""Writes entries to the access log (audit trail)."""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AccessLog, User


def log_access(
    db: Session,
    request: Request | None,
    action: str,
    user: User | None = None,
    username: str = "",
    document_id: str | None = None,
    success: bool = True,
    detail: str = "",
) -> None:
    ip_address = ""
    user_agent = ""
    if request is not None:
        ip_address = request.client.host if request.client else ""
        user_agent = (request.headers.get("user-agent") or "")[:255]
    db.add(
        AccessLog(
            user_id=user.id if user else None,
            username=user.username if user else username,
            action=action,
            document_id=document_id,
            success=success,
            ip_address=ip_address,
            user_agent=user_agent,
            detail=detail[:255],
        )
    )
    db.commit()
