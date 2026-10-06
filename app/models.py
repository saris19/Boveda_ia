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

    # AI results
    category: Mapped[str] = mapped_column(String(50), default="Sin clasificar")
    category_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sensitivity: Mapped[SensitivityLevel] = mapped_column(Enum(SensitivityLevel), default=SensitivityLevel.PUBLIC)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    sensitive_findings: Mapped[dict] = mapped_column(JSON, default=dict)   # masked samples only
    keywords: Mapped[list] = mapped_column(JSON, default=list)

    owner: Mapped[User] = relationship(back_populates="documents")
    permissions: Mapped[list["DocumentPermission"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


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
    """Audit trail. Also the dataset for the future suspicious-access detector."""

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
