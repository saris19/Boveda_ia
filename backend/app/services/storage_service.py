"""Storage of encrypted blobs. Only ciphertext ever reaches this layer.

Backends (VAULT_STORAGE_BACKEND):
  - disk:     data/storage/<blob_id>.enc
  - database: encrypted_blobs table (for hosts with an ephemeral filesystem such as Render free)

Each stored content (current document or an old version) has its own blob id. Documents created
before versioning use their document id as blob id, so old references keep working.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import config
from app.models import EncryptedBlob

DATABASE_PREFIX = "db://"


class BlobNotFoundError(Exception):
    pass


def save_blob(db: Session, blob_id: str, ciphertext: bytes) -> str:
    """Store the ciphertext and return the storage reference (saved in storage_path)."""
    if config.STORAGE_BACKEND == "database":
        db.add(EncryptedBlob(document_id=blob_id, data=ciphertext))
        return f"{DATABASE_PREFIX}{blob_id}"
    path = config.STORAGE_DIR / f"{blob_id}.enc"
    path.write_bytes(ciphertext)
    return path.name


def load_blob(db: Session, storage_path: str) -> bytes:
    if storage_path.startswith(DATABASE_PREFIX):
        blob = db.get(EncryptedBlob, storage_path[len(DATABASE_PREFIX):])
        if blob is None:
            raise BlobNotFoundError(storage_path)
        return blob.data
    path = config.STORAGE_DIR / storage_path
    if not path.exists():
        raise BlobNotFoundError(storage_path)
    return path.read_bytes()


def delete_blob(db: Session, storage_path: str) -> None:
    if storage_path.startswith(DATABASE_PREFIX):
        blob = db.get(EncryptedBlob, storage_path[len(DATABASE_PREFIX):])
        if blob is not None:
            db.delete(blob)
        return
    (config.STORAGE_DIR / storage_path).unlink(missing_ok=True)
