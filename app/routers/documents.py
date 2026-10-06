"""Encrypted document vault: upload, list, download, share, delete, and AI analysis."""
from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.ai.analyzer import analyze_text
from app.ai.text_extractor import extract_text
from app.crypto.vault_crypto import IntegrityError, decrypt_document, encrypt_document
from app.database import get_db
from app.models import AccessLevel, Document, DocumentPermission, Role, User
from app.schemas import AnalysisResult, DocumentOut, PermissionOut, ShareRequest
from app.security import get_current_user, require_roles
from app.services.audit_service import log_access
from app.services.permission_service import get_access_level, list_accessible_documents
from app.services.storage_service import BlobNotFoundError, delete_blob, load_blob, save_blob

router = APIRouter(prefix="/api/documents", tags=["Documentos"])
uploader_roles = require_roles(Role.ADMIN, Role.EDITOR)


def _to_out(document: Document, access: AccessLevel) -> DocumentOut:
    out = DocumentOut.model_validate(document)
    out.owner_username = document.owner.username if document.owner else ""
    out.my_access = access.value
    return out


def _get_document_or_404(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return document


def _require_access(
    db: Session, request: Request, user: User, document: Document, action: str, needed: AccessLevel
) -> AccessLevel:
    access = get_access_level(db, user, document)
    allowed = access is not None and (needed == AccessLevel.READ or access == AccessLevel.MANAGE)
    if not allowed:
        log_access(db, request, action, user=user, document_id=document.id, success=False, detail="acceso denegado")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes acceso a este documento.")
    return access


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    filename = Path(file.filename or "archivo").name
    if Path(filename).suffix.lower() not in config.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no permitido. Usa: {allowed}")
    content = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera el tamaño máximo permitido.")
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    return content, filename


@router.post("", response_model=DocumentOut, status_code=201, summary="Subir y cifrar documento")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(uploader_roles),
):
    content, filename = await _read_upload(file)

    # 1) AI analysis on the plaintext, in memory only
    analysis = analyze_text(extract_text(content, filename))

    # 2) Encrypt and store only the ciphertext
    document_id = str(uuid.uuid4())
    payload = encrypt_document(content, document_id)
    storage_path = save_blob(db, document_id, payload.ciphertext)

    document = Document(
        id=document_id,
        original_name=filename,
        content_type=file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
        size_bytes=len(content),
        sha256=payload.sha256,
        owner_id=current_user.id,
        wrapped_key=payload.wrapped_key,
        key_nonce=payload.key_nonce,
        data_nonce=payload.data_nonce,
        storage_path=storage_path,
        category=analysis.category,
        category_confidence=analysis.category_confidence,
        sensitivity=analysis.sensitivity,
        risk_score=analysis.risk_score,
        sensitive_findings=analysis.sensitive_findings,
        keywords=analysis.keywords,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    log_access(
        db, request, "upload", user=current_user, document_id=document_id,
        detail=f"{filename} | {analysis.category} | {analysis.sensitivity.value}",
    )
    return _to_out(document, AccessLevel.MANAGE)


@router.post("/analyze", response_model=AnalysisResult, summary="Analizar con IA sin guardar")
async def analyze_only(file: UploadFile = File(...), _: User = Depends(get_current_user)):
    content, filename = await _read_upload(file)
    return analyze_text(extract_text(content, filename))


@router.get("", response_model=list[DocumentOut], summary="Listar mis documentos accesibles")
def list_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [
        _to_out(doc, get_access_level(db, current_user, doc) or AccessLevel.READ)
        for doc in list_accessible_documents(db, current_user)
    ]


@router.get("/{document_id}", response_model=DocumentOut, summary="Ver metadatos de un documento")
def get_document(
    document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    document = _get_document_or_404(db, document_id)
    access = _require_access(db, request, current_user, document, "view", AccessLevel.READ)
    log_access(db, request, "view", user=current_user, document_id=document.id)
    return _to_out(document, access)


@router.get("/{document_id}/download", summary="Descargar (descifrar) documento")
def download_document(
    document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    document = _get_document_or_404(db, document_id)
    _require_access(db, request, current_user, document, "download", AccessLevel.READ)

    try:
        ciphertext = load_blob(db, document.storage_path, document.id)
    except BlobNotFoundError:
        raise HTTPException(status_code=410, detail="El archivo cifrado no se encuentra en el almacenamiento.")
    try:
        plaintext = decrypt_document(
            ciphertext, document.data_nonce, document.wrapped_key,
            document.key_nonce, document.id, document.sha256,
        )
    except IntegrityError as error:
        log_access(db, request, "download", user=current_user, document_id=document.id, success=False, detail=str(error))
        raise HTTPException(status_code=409, detail=f"Falla de integridad: {error}")

    log_access(db, request, "download", user=current_user, document_id=document.id)
    return Response(
        content=plaintext,
        media_type=document.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.original_name)}"},
    )


@router.get("/{document_id}/permissions", response_model=list[PermissionOut], summary="Ver con quién está compartido")
def list_permissions(
    document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    document = _get_document_or_404(db, document_id)
    _require_access(db, request, current_user, document, "view_permissions", AccessLevel.MANAGE)
    return document.permissions


@router.post("/{document_id}/share", response_model=PermissionOut, status_code=201, summary="Compartir con usuario o rol")
def share_document(
    document_id: str,
    payload: ShareRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _get_document_or_404(db, document_id)
    _require_access(db, request, current_user, document, "share", AccessLevel.MANAGE)

    if (payload.username is None) == (payload.role is None):
        raise HTTPException(status_code=400, detail="Indica un usuario o un rol (solo uno).")

    target_user = None
    if payload.username:
        target_user = db.scalar(select(User).where(User.username == payload.username))
        if target_user is None:
            raise HTTPException(status_code=404, detail="El usuario no existe.")
        if target_user.id == document.owner_id:
            raise HTTPException(status_code=400, detail="El propietario ya tiene acceso total.")

    target_filter = (
        DocumentPermission.user_id == target_user.id if target_user else DocumentPermission.role == payload.role
    )
    permission = db.scalar(
        select(DocumentPermission).where(DocumentPermission.document_id == document.id, target_filter)
    )
    if permission is None:
        permission = DocumentPermission(
            document_id=document.id,
            user_id=target_user.id if target_user else None,
            role=None if target_user else payload.role,
            granted_by=current_user.id,
        )
        db.add(permission)
    permission.access_level = payload.access_level
    db.commit()
    db.refresh(permission)

    target = f"usuario {target_user.username}" if target_user else f"rol {payload.role.value}"
    log_access(db, request, "share", user=current_user, document_id=document.id,
               detail=f"{target} -> {payload.access_level.value}")
    return permission


@router.delete("/{document_id}/permissions/{permission_id}", status_code=204, summary="Revocar acceso")
def revoke_permission(
    document_id: str,
    permission_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _get_document_or_404(db, document_id)
    _require_access(db, request, current_user, document, "revoke", AccessLevel.MANAGE)
    permission = db.get(DocumentPermission, permission_id)
    if permission is None or permission.document_id != document.id:
        raise HTTPException(status_code=404, detail="Permiso no encontrado.")
    db.delete(permission)
    db.commit()
    log_access(db, request, "revoke", user=current_user, document_id=document.id, detail=f"permiso {permission_id}")


@router.delete("/{document_id}", status_code=204, summary="Eliminar documento")
def delete_document(
    document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    document = _get_document_or_404(db, document_id)
    _require_access(db, request, current_user, document, "delete", AccessLevel.MANAGE)
    if current_user.role == Role.VIEWER:
        raise HTTPException(status_code=403, detail="Los lectores no pueden eliminar documentos.")

    delete_blob(db, document.storage_path, document.id)
    name = document.original_name
    db.delete(document)
    db.commit()
    log_access(db, request, "delete", user=current_user, document_id=document_id, detail=name)
