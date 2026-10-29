"""Access-control rules (RBAC + per-document sharing)."""
from __future__ import annotations

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.models import AccessLevel, Document, DocumentPermission, Role, SensitivityLevel, User
from app.services.policy_service import role_grant_allowed


def get_access_level(db: Session, user: User, document: Document) -> AccessLevel | None:
    """Return the effective access level of `user` over `document`, or None if no access.

    Rules (highest wins):
      1. Admins manage every document.
      2. The owner manages their own document.
      3. An explicit grant to the user or to the user's role.
    Sensitivity policy: role grants are ignored for restricted documents, and for confidential
    documents they only apply to editors and admins (see policy_service).
    """
    if document.deleted_at is not None:
        return AccessLevel.MANAGE if user.role == Role.ADMIN or document.owner_id == user.id else None
    if user.role == Role.ADMIN or document.owner_id == user.id:
        return AccessLevel.MANAGE

    grants = db.scalars(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            or_(DocumentPermission.user_id == user.id, DocumentPermission.role == user.role),
        )
    ).all()
    grants = [
        grant for grant in grants
        if grant.user_id == user.id or role_grant_allowed(document.sensitivity, user.role)
    ]
    if not grants:
        return None
    if any(grant.access_level == AccessLevel.MANAGE for grant in grants):
        # Viewers can never manage, even if granted.
        return AccessLevel.READ if user.role == Role.VIEWER else AccessLevel.MANAGE
    return AccessLevel.READ


def accessible_documents_query(user: User) -> Select:
    """SELECT of the (non-deleted) documents `user` can read (reused by listing, search and statistics)."""
    query = select(Document).where(Document.deleted_at.is_(None)).order_by(Document.uploaded_at.desc())
    if user.role != Role.ADMIN:
        user_grants = select(DocumentPermission.document_id).where(DocumentPermission.user_id == user.id)
        role_grants = select(DocumentPermission.document_id).where(DocumentPermission.role == user.role)
        # Same sensitivity policy as get_access_level, expressed in SQL
        if user.role == Role.VIEWER:
            allowed_levels = [SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL]
        else:
            allowed_levels = [SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL, SensitivityLevel.CONFIDENTIAL]
        query = query.where(
            or_(
                Document.owner_id == user.id,
                Document.id.in_(user_grants),
                (Document.id.in_(role_grants)) & (Document.sensitivity.in_(allowed_levels)),
            )
        )
    return query


def list_accessible_documents(db: Session, user: User) -> list[Document]:
    return list(db.scalars(accessible_documents_query(user)).all())
