"""Access-control rules (RBAC + per-document sharing)."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import AccessLevel, Document, DocumentPermission, Role, User


def get_access_level(db: Session, user: User, document: Document) -> AccessLevel | None:
    """Return the effective access level of `user` over `document`, or None if no access.

    Rules (highest wins):
      1. Admins manage every document.
      2. The owner manages their own document.
      3. An explicit grant to the user or to the user's role.
    """
    if user.role == Role.ADMIN or document.owner_id == user.id:
        return AccessLevel.MANAGE

    grants = db.scalars(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            or_(DocumentPermission.user_id == user.id, DocumentPermission.role == user.role),
        )
    ).all()
    if not grants:
        return None
    if any(grant.access_level == AccessLevel.MANAGE for grant in grants):
        # Viewers can never manage, even if granted.
        return AccessLevel.READ if user.role == Role.VIEWER else AccessLevel.MANAGE
    return AccessLevel.READ


def list_accessible_documents(db: Session, user: User) -> list[Document]:
    query = select(Document).order_by(Document.uploaded_at.desc())
    if user.role != Role.ADMIN:
        shared_ids = select(DocumentPermission.document_id).where(
            or_(DocumentPermission.user_id == user.id, DocumentPermission.role == user.role)
        )
        query = query.where(or_(Document.owner_id == user.id, Document.id.in_(shared_ids)))
    return list(db.scalars(query).all())
