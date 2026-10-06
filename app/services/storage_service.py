"""Storage of encrypted blobs. Only ciphertext ever reaches this layer.

Backends (VAULT_STORAGE_BACKEND):
  - disk:     data/storage/<id>.enc
  - database: encrypted_blobs table (for hosts with an ephemeral filesystem such as Render free)
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import config
from app.models import EncryptedBlob

DATABASE_PREFIX = "db://"


class BlobNotFoundError(Exception):
    pass


def save_blob(db: Session, document_id: str, ciphertext: bytes) -> str:
    """Store the ciphertext and return the storage reference saved in Document.storage_path."""
    if config.STORAGE_BACKEND == "database":
        db.add(EncryptedBlob(document_id=document_id, data=ciphertext))
        return f"{DATABASE_PREFIX}{document_id}"
    path = config.STORAGE_DIR / f"{document_id}.enc"
    path.write_bytes(ciphertext)
    return path.name


def load_blob(db: Session, storage_path: str, document_id: str) -> bytes:
    if storage_path.startswith(DATABASE_PREFIX):
        blob = db.get(EncryptedBlob, document_id)
        if blob is None:
            raise BlobNotFoundError(document_id)
        return blob.data
    path = config.STORAGE_DIR / storage_path
    if not path.exists():
        raise BlobNotFoundError(document_id)
    return path.read_bytes()


def delete_blob(db: Session, storage_path: str, document_id: str) -> None:
    if storage_path.startswith(DATABASE_PREFIX):
        blob = db.get(EncryptedBlob, document_id)
        if blob is not None:
            db.delete(blob)
        return
    (config.STORAGE_DIR / storage_path).unlink(missing_ok=True)
