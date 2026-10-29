"""Encrypted document vault: upload, list, download, versions, share, classification, recycle bin."""
from __future__ import annotations

import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.ai.analyzer import analyze_text
from app.ai.classifier import UNCLASSIFIED_LABEL, privacy_safe_training_text
from app.ai.search_index import build_blind_index
from app.ai.text_extractor import extract_text
from app.ai.training_data import TRAINING_SAMPLES
from app.crypto.keyring import active_key, get_key
from app.crypto.vault_crypto import IntegrityError, decrypt_document, encrypt_document
from app.database import get_db
from app.models import (
    AccessLevel,
    ClassificationFeedback,
    Document,
    DocumentPermission,
    DocumentVersion,
    Role,
    User,
)
from app.schemas import (
    AnalysisResult,
    ClassificationUpdate,
    DocumentOut,
    PermissionOut,
    ShareRequest,
    VersionOut,
)
from app.security import get_current_user, require_roles
from app.services.audit_service import log_access
from app.services.feedback_service import retrain_from_feedback
from app.services.permission_service import get_access_level, list_accessible_documents
from app.services.policy_service import role_grant_error
from app.services.storage_service import BlobNotFoundError, load_blob, save_blob

router = APIRouter(prefix="/api/documents", tags=["Documentos"])
uploader_roles = require_roles(Role.ADMIN, Role.EDITOR)
VALID_CATEGORIES = set(TRAINING_SAMPLES) | {UNCLASSIFIED_LABEL}


def to_document_out(document: Document, access: AccessLevel) -> DocumentOut:
    out = DocumentOut.model_validate(document)
    out.owner_username = document.owner.username if document.owner else ""
    out.my_access = access.value
    return out


def get_active_document_or_404(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return document


def require_access(
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


def _content_type(file: UploadFile | None, filename: str) -> str:
    return (file.content_type if file else None) or mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _check_download_block(user: User) -> None:
    blocked = user.downloads_blocked_until
    if blocked and (blocked if blocked.tzinfo else blocked.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Tus descargas están pausadas temporalmente por actividad inusual. Un administrador puede reactivarlas.",
        )


def decrypt_current(db: Session, document: Document) -> bytes:
    return decrypt_document(
        load_blob(db, document.storage_path), document.data_nonce, document.wrapped_key, document.key_nonce,
        document.id, document.sha256, kek=get_key(db, document.key_version), version_number=document.version_number,
    )


def _decrypt_version(db: Session, version: DocumentVersion) -> bytes:
    return decrypt_document(
        load_blob(db, version.storage_path), version.data_nonce, version.wrapped_key, version.key_nonce,
        version.document_id, version.sha256, kek=get_key(db, version.key_version),
        version_number=version.version_number,
    )


def _apply_content(db: Session, document: Document, content: bytes, filename: str, content_type: str) -> AnalysisResult:
    """Analyze, index and encrypt `content` as the document's current version (version_number already set)."""
    text = extract_text(content, filename)
    analysis = analyze_text(text)
    key_version, kek = active_key(db)
    payload = encrypt_document(content, document.id, kek=kek, version_number=document.version_number)
    blob_id = document.id if document.version_number == 1 else str(uuid.uuid4())

    document.original_name = filename
    document.content_type = content_type
    document.size_bytes = len(content)
    document.sha256 = payload.sha256
    document.wrapped_key = payload.wrapped_key
    document.key_nonce = payload.key_nonce
    document.data_nonce = payload.data_nonce
    document.key_version = key_version
    document.storage_path = save_blob(db, blob_id, payload.ciphertext)
    document.category = analysis.category
    document.category_confidence = analysis.category_confidence
    document.sensitivity = analysis.sensitivity
    document.risk_score = analysis.risk_score
    document.sensitive_findings = analysis.sensitive_findings
    document.keywords = analysis.keywords
    document.manual_classification = False
    document.search_index = build_blind_index(f"{filename} {text}")
    return analysis


def _archive_current(db: Session, document: Document, uploaded_by: int | None) -> None:
    db.add(
        DocumentVersion(
            document_id=document.id,
            version_number=document.version_number,
            original_name=document.original_name,
            content_type=document.content_type,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            wrapped_key=document.wrapped_key,
            key_nonce=document.key_nonce,
            data_nonce=document.data_nonce,
            key_version=document.key_version,
            storage_path=document.storage_path,
            uploaded_by=uploaded_by,
            uploaded_at=document.uploaded_at,
            category=document.category,
            sensitivity=document.sensitivity,
            risk_score=document.risk_score,
        )
    )


def _file_response(content: bytes, content_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ---------------------------------------------------------------- upload / list / view


@router.post("", response_model=DocumentOut, status_code=201, summary="Subir y cifrar documento")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(uploader_roles),
):
    content, filename = await _read_upload(file)
    document = Document(id=str(uuid.uuid4()), owner_id=current_user.id, version_number=1)
    analysis = _apply_content(db, document, content, filename, _content_type(file, filename))
    db.add(document)
    db.commit()
    db.refresh(document)
    log_access(
        db, request, "upload", user=current_user, document_id=document.id,
        detail=f"{filename} | {analysis.category} | {analysis.sensitivity.value}",
    )
    return to_document_out(document, AccessLevel.MANAGE)


@router.post("/analyze", response_model=AnalysisResult, summary="Analizar con IA sin guardar")
async def analyze_only(file: UploadFile = File(...), _: User = Depends(get_current_user)):
    content, filename = await _read_upload(file)
    return analyze_text(extract_text(content, filename))


@router.get("", response_model=list[DocumentOut], summary="Listar mis documentos accesibles")
def list_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [
        to_document_out(doc, get_access_level(db, current_user, doc) or AccessLevel.READ)
        for doc in list_accessible_documents(db, current_user)
    ]


@router.get("/{document_id}", response_model=DocumentOut, summary="Ver metadatos de un documento")
def get_document(
    document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    document = get_active_document_or_404(db, document_id)
    access = require_access(db, request, current_user, document, "view", AccessLevel.READ)
    log_access(db, request, "view", user=current_user, document_id=document.id)
    return to_document_out(document, access)


@router.get("/{document_id}/download", summary="Descargar (descifrar) la versión actual")
def download_document(
    document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    document = get_active_document_or_404(db, document_id)
    require_access(db, request, current_user, document, "download", AccessLevel.READ)
    _check_download_block(current_user)
    try:
        plaintext = decrypt_current(db, document)
    except BlobNotFoundError:
        raise HTTPException(status_code=410, detail="El archivo cifrado no se encuentra en el almacenamiento.")
    except IntegrityError as error:
        log_access(db, request, "download", user=current_user, document_id=document.id, success=False, detail=str(error))
        raise HTTPException(status_code=409, detail=f"Falla de integridad: {error}")

    log_access(db, request, "download", user=current_user, document_id=document.id,
               detail=f"v{document.version_number} | {document.sensitivity.value}")
    return _file_response(plaintext, document.content_type, document.original_name)


# ---------------------------------------------------------------- versions


@router.get("/{document_id}/versions", response_model=list[VersionOut], summary="Historial de versiones")
def list_versions(
    document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    document = get_active_document_or_404(db, document_id)
    require_access(db, request, current_user, document, "view", AccessLevel.READ)
    names = dict(db.execute(select(User.id, User.username)).all())
    current = VersionOut(
        version_number=document.version_number, original_name=document.original_name,
        size_bytes=document.size_bytes, sha256=document.sha256, uploaded_at=document.uploaded_at,
        uploaded_by_username=names.get(document.owner_id, ""), category=document.category,
        sensitivity=document.sensitivity, risk_score=document.risk_score, is_current=True,
    )
    older = [
        VersionOut(
            version_number=v.version_number, original_name=v.original_name, size_bytes=v.size_bytes,
            sha256=v.sha256, uploaded_at=v.uploaded_at, uploaded_by_username=names.get(v.uploaded_by, ""),
            category=v.category, sensitivity=v.sensitivity, risk_score=v.risk_score,
        )
        for v in document.versions
    ]
    return [current, *older]


@router.post("/{document_id}/versions", response_model=DocumentOut, status_code=201, summary="Subir nueva versión")
async def upload_version(
    document_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(uploader_roles),
):
    document = get_active_document_or_404(db, document_id)
    access = require_access(db, request, current_user, document, "new_version", AccessLevel.MANAGE)
    content, filename = await _read_upload(file)
    _archive_current(db, document, uploaded_by=document.owner_id if document.version_number == 1 else None)
    document.version_number += 1
    document.uploaded_at = datetime.now(timezone.utc)
    analysis = _apply_content(db, document, content, filename, _content_type(file, filename))
    db.commit()
    db.refresh(document)
    log_access(db, request, "new_version", user=current_user, document_id=document.id,
               detail=f"v{document.version_number} | {analysis.category} | {analysis.sensitivity.value}")
    return to_document_out(document, access)


def _get_version(document: Document, number: int) -> DocumentVersion:
    version = next((v for v in document.versions if v.version_number == number), None)
    if version is None:
        raise HTTPException(status_code=404, detail="Versión no encontrada.")
    return version


@router.get("/{document_id}/versions/{number}/download", summary="Descargar una versión anterior")
def download_version(
    document_id: str,
    number: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_active_document_or_404(db, document_id)
    require_access(db, request, current_user, document, "download", AccessLevel.READ)
    _check_download_block(current_user)
    if number == document.version_number:
        return download_document(document_id, request, db, current_user)
    version = _get_version(document, number)
    try:
        plaintext = _decrypt_version(db, version)
    except (BlobNotFoundError, IntegrityError) as error:
        raise HTTPException(status_code=409, detail=f"No se pudo descifrar la versión: {error}")
    log_access(db, request, "download", user=current_user, document_id=document.id,
               detail=f"v{number} | {version.sensitivity.value}")
    return _file_response(plaintext, version.content_type, version.original_name)


@router.post("/{document_id}/versions/{number}/restore", response_model=DocumentOut, summary="Restaurar una versión")
def restore_version(
    document_id: str,
    number: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(uploader_roles),
):
    """Restoring keeps the history: the old content becomes a new, latest version."""
    document = get_active_document_or_404(db, document_id)
    access = require_access(db, request, current_user, document, "restore_version", AccessLevel.MANAGE)
    version = _get_version(document, number)
    content = _decrypt_version(db, version)
    _archive_current(db, document, uploaded_by=None)
    document.version_number += 1
    document.uploaded_at = datetime.now(timezone.utc)
    _apply_content(db, document, content, version.original_name, version.content_type)
    db.commit()
    db.refresh(document)
    log_access(db, request, "restore_version", user=current_user, document_id=document.id,
               detail=f"v{number} restaurada como v{document.version_number}")
    return to_document_out(document, access)


# ---------------------------------------------------------------- classification feedback


@router.patch("/{document_id}/classification", response_model=DocumentOut, summary="Corregir la clasificación de la IA")
def update_classification(
    document_id: str,
    payload: ClassificationUpdate,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(uploader_roles),
):
    document = get_active_document_or_404(db, document_id)
    access = require_access(db, request, current_user, document, "classify", AccessLevel.MANAGE)
    if payload.category is None and payload.sensitivity is None:
        raise HTTPException(status_code=400, detail="Indica la categoría o la sensibilidad a corregir.")
    if payload.category is not None and payload.category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="Categoría no válida.")

    changes = []
    if payload.category and payload.category != document.category:
        # Feedback for retraining: only privacy-filtered common words of the content are kept.
        try:
            text = extract_text(decrypt_current(db, document), document.original_name)
        except (BlobNotFoundError, IntegrityError):
            text = ""
        db.add(
            ClassificationFeedback(
                document_id=document.id,
                predicted_category=document.category,
                corrected_category=payload.category,
                training_text=privacy_safe_training_text(text)[:4000],
                user_id=current_user.id,
            )
        )
        changes.append(f"categoría {document.category} → {payload.category}")
        document.category = payload.category
        document.category_confidence = 1.0
        background.add_task(retrain_from_feedback)
    if payload.sensitivity and payload.sensitivity != document.sensitivity:
        changes.append(f"sensibilidad {document.sensitivity.value} → {payload.sensitivity.value}")
        document.sensitivity = payload.sensitivity
    if changes:
        document.manual_classification = True
        db.commit()
        db.refresh(document)
        log_access(db, request, "classify", user=current_user, document_id=document.id, detail="; ".join(changes))
    return to_document_out(document, access)


# ---------------------------------------------------------------- sharing


@router.get("/{document_id}/permissions", response_model=list[PermissionOut], summary="Ver con quién está compartido")
def list_permissions(
    document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    document = get_active_document_or_404(db, document_id)
    require_access(db, request, current_user, document, "view_permissions", AccessLevel.MANAGE)
    return document.permissions


@router.post("/{document_id}/share", response_model=PermissionOut, status_code=201, summary="Compartir con usuario o rol")
def share_document(
    document_id: str,
    payload: ShareRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_active_document_or_404(db, document_id)
    require_access(db, request, current_user, document, "share", AccessLevel.MANAGE)

    if (payload.username is None) == (payload.role is None):
        raise HTTPException(status_code=400, detail="Indica un usuario o un rol (solo uno).")
    if payload.role is not None:
        error = role_grant_error(document.sensitivity, payload.role)
        if error:
            log_access(db, request, "share", user=current_user, document_id=document.id, success=False,
                       detail=f"política de sensibilidad ({document.sensitivity.value})")
            raise HTTPException(status_code=400, detail=error)

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
    document = get_active_document_or_404(db, document_id)
    require_access(db, request, current_user, document, "revoke", AccessLevel.MANAGE)
    permission = db.get(DocumentPermission, permission_id)
    if permission is None or permission.document_id != document.id:
        raise HTTPException(status_code=404, detail="Permiso no encontrado.")
    db.delete(permission)
    db.commit()
    log_access(db, request, "revoke", user=current_user, document_id=document.id, detail=f"permiso {permission_id}")


# ---------------------------------------------------------------- delete (to the recycle bin)


@router.delete("/{document_id}", status_code=204, summary="Enviar a la papelera")
def delete_document(
    document_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    document = get_active_document_or_404(db, document_id)
    require_access(db, request, current_user, document, "delete", AccessLevel.MANAGE)
    if current_user.role == Role.VIEWER:
        raise HTTPException(status_code=403, detail="Los lectores no pueden eliminar documentos.")
    document.deleted_at = datetime.now(timezone.utc)
    document.deleted_by = current_user.id
    db.commit()
    log_access(db, request, "delete", user=current_user, document_id=document_id,
               detail=f"{document.original_name} → papelera")
