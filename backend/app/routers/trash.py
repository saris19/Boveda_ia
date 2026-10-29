"""Recycle bin: deleted documents are kept for VAULT_TRASH_DAYS and can be restored or purged."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import AccessLevel, Document, Role, User
from app.routers.documents import to_document_out
from app.schemas import DeletedDocumentOut
from app.security import get_current_user, require_roles
from app.services.audit_service import log_access
from app.services.storage_service import delete_blob

router = APIRouter(prefix="/api/trash", tags=["Papelera"])
uploader_roles = require_roles(Role.ADMIN, Role.EDITOR)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def purge_document(db: Session, document: Document) -> None:
    """Permanently delete a document: every encrypted blob (all versions) and its rows."""
    for version in document.versions:
        delete_blob(db, version.storage_path)
    delete_blob(db, document.storage_path)
    db.delete(document)


def purge_expired(db: Session) -> int:
    limit = datetime.now(timezone.utc) - timedelta(days=config.TRASH_RETENTION_DAYS)
    expired = [
        d for d in db.scalars(select(Document).where(Document.deleted_at.is_not(None))).all()
        if _as_utc(d.deleted_at) < limit
    ]
    for document in expired:
        purge_document(db, document)
    if expired:
        db.commit()
    return len(expired)


def _get_deleted(db: Session, user: User, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is None:
        raise HTTPException(status_code=404, detail="El documento no está en la papelera.")
    if user.role != Role.ADMIN and document.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el propietario o un administrador pueden hacer esto.")
    return document


@router.get("", response_model=list[DeletedDocumentOut], summary="Documentos en la papelera")
def list_trash(db: Session = Depends(get_db), current_user: User = Depends(uploader_roles)):
    purge_expired(db)
    query = select(Document).where(Document.deleted_at.is_not(None)).order_by(Document.deleted_at.desc())
    if current_user.role != Role.ADMIN:
        query = query.where(Document.owner_id == current_user.id)
    names = dict(db.execute(select(User.id, User.username)).all())
    result = []
    for document in db.scalars(query).all():
        out = DeletedDocumentOut(**to_document_out(document, AccessLevel.MANAGE).model_dump())
        out.deleted_at = document.deleted_at
        out.deleted_by_username = names.get(document.deleted_by, "")
        out.purge_at = _as_utc(document.deleted_at) + timedelta(days=config.TRASH_RETENTION_DAYS)
        result.append(out)
    return result


@router.post("/{document_id}/restore", status_code=204, summary="Restaurar desde la papelera")
def restore(document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(uploader_roles)):
    document = _get_deleted(db, current_user, document_id)
    document.deleted_at = None
    document.deleted_by = None
    db.commit()
    log_access(db, request, "restore", user=current_user, document_id=document_id, detail=document.original_name)


@router.delete("/{document_id}", status_code=204, summary="Eliminar definitivamente")
def purge(document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(uploader_roles)):
    document = _get_deleted(db, current_user, document_id)
    name = document.original_name
    purge_document(db, document)
    db.commit()
    log_access(db, request, "purge", user=current_user, document_id=document_id, detail=f"{name} eliminado definitivamente")
