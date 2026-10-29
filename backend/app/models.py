"""Database models: users, documents, sharing permissions and the access log."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    ADMIN = "admin"      # full control, user management, audit log
    EDITOR = "editor"    # upload, share and delete own documents
    VIEWER = "viewer"    # read documents shared with them


class SensitivityLevel(str, enum.Enum):
    PUBLIC = "publico"
    INTERNAL = "interno"
    CONFIDENTIAL = "confidencial"
    RESTRICTED = "restringido"


class AccessLevel(str, enum.Enum):
    READ = "read"        # view metadata + download
    MANAGE = "manage"    # read + share + delete


class AlertSeverity(str, enum.Enum):
    LOW = "baja"
    MEDIUM = "media"
    HIGH = "alta"
    CRITICAL = "critica"


class AlertStatus(str, enum.Enum):
    OPEN = "abierta"
    IN_REVIEW = "en_revision"
    RESOLVED = "resuelta"
    FALSE_POSITIVE = "falso_positivo"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Automatic response to mass downloads: downloads are paused until this moment
    downloads_blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    documents: Mapped[list["Document"]] = relationship(back_populates="owner")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))          # hash of the plaintext, for integrity check
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # Envelope encryption material (the plaintext data key is never stored)
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    key_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    data_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    storage_path: Mapped[str] = mapped_column(String(255))
    key_version: Mapped[int] = mapped_column(Integer, default=0)       # 0 = wrapped directly with the root key
    version_number: Mapped[int] = mapped_column(Integer, default=1)    # current version of the content

    # Recycle bin (soft delete)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # AI results
    category: Mapped[str] = mapped_column(String(50), default="Sin clasificar")
    category_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sensitivity: Mapped[SensitivityLevel] = mapped_column(Enum(SensitivityLevel), default=SensitivityLevel.PUBLIC)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    sensitive_findings: Mapped[dict] = mapped_column(JSON, default=dict)   # masked samples only
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    manual_classification: Mapped[bool] = mapped_column(Boolean, default=False)  # corrected by a person
    # Blind index (HMAC tokens of the content words). Deferred: only loaded by the search service.
    search_index: Mapped[list | None] = mapped_column(JSON, nullable=True, deferred=True)

    owner: Mapped[User] = relationship(back_populates="documents")
    permissions: Mapped[list["DocumentPermission"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_number.desc()"
    )


class DocumentVersion(Base):
    """Previous versions of a document's content (each one encrypted with its own data key)."""

    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    key_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    data_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(255))
    uploaded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    category: Mapped[str] = mapped_column(String(50), default="")
    sensitivity: Mapped[SensitivityLevel] = mapped_column(Enum(SensitivityLevel), default=SensitivityLevel.PUBLIC)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped[Document] = relationship(back_populates="versions")


class MasterKey(Base):
    """Keyring: data master keys, each one wrapped with the root key (VAULT_MASTER_KEY).

    Rotating creates a new version and re-wraps every document key with it; the old one is retired.
    """

    __tablename__ = "master_keys"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ClassificationFeedback(Base):
    """Category corrections made by people; used to retrain the classifier.

    Only normalized common words are stored (no numbers, no capitalized words that could be names).
    """

    __tablename__ = "classification_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36))
    predicted_category: Mapped[str] = mapped_column(String(50))
    corrected_category: Mapped[str] = mapped_column(String(50))
    training_text: Mapped[str] = mapped_column(String(4000), default="")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SecurityAlert(Base):
    """Suspicious-access alert raised by the rules engine or the anomaly model."""

    __tablename__ = "security_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    rule: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity))
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.OPEN, index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="")
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)          # 0-100
    event_count: Mapped[int] = mapped_column(Integer, default=1)
    response: Mapped[str] = mapped_column(String(200), default="")     # automatic action taken, if any
    resolved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(String(500), default="")


class EncryptedBlob(Base):
    """Ciphertext of a document when VAULT_STORAGE_BACKEND=database (kept apart so listings never load blobs)."""

    __tablename__ = "encrypted_blobs"

    document_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class DocumentPermission(Base):
    """Grants access to a document either to a single user or to every user with a role."""

    __tablename__ = "document_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    role: Mapped[Role | None] = mapped_column(Enum(Role), nullable=True)
    access_level: Mapped[AccessLevel] = mapped_column(Enum(AccessLevel), default=AccessLevel.READ)
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[Document] = relationship(back_populates="permissions")


class AccessLog(Base):
    """Audit trail. Also the dataset of the suspicious-access detector."""

    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="")
    action: Mapped[str] = mapped_column(String(30))          # login, upload, download, view, share, delete, ...
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str] = mapped_column(String(255), default="")
