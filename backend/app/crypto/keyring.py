"""Key hierarchy and master-key rotation.

    VAULT_MASTER_KEY (root, environment)          never stored in the database
        └── master key vN (table master_keys)      random, wrapped with the root key
              └── data key of each document        random, wrapped with the active master key
                    └── document content           AES-256-GCM

Version 0 means "wrapped directly with the root key" (documents created before the first rotation).
Rotating generates a new master key and re-wraps every data key (current content and old versions);
the encrypted contents themselves are not touched, so rotation is fast and safe.
"""
from __future__ import annotations

from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crypto.vault_crypto import document_aad, load_master_key, unwrap_key, wrap_key
from app.models import Document, DocumentVersion, MasterKey

_cache: dict[int, bytes] = {}


def _keyring_aad(version: int) -> bytes:
    return f"boveda-ia/keyring/v{version}".encode()


def get_key(db: Session, version: int) -> bytes:
    if version == 0:
        return load_master_key()
    if version not in _cache:
        row = db.get(MasterKey, version)
        if row is None:
            raise LookupError(f"No existe la llave maestra versión {version}.")
        _cache[version] = unwrap_key(load_master_key(), row.wrapped_key, row.nonce, _keyring_aad(version))
    return _cache[version]


def active_key(db: Session) -> tuple[int, bytes]:
    row = db.scalar(select(MasterKey).where(MasterKey.active.is_(True)).order_by(MasterKey.version.desc()))
    version = row.version if row else 0
    return version, get_key(db, version)


def keyring_status(db: Session) -> dict:
    version, _ = active_key(db)
    rows = db.scalars(select(MasterKey).order_by(MasterKey.version.desc())).all()
    by_version = dict(
        db.execute(select(Document.key_version, func.count()).group_by(Document.key_version)).all()
    )
    return {
        "active_version": version,
        "rotations": len(rows),
        "last_rotation": rows[0].created_at if rows else None,
        "documents_by_key_version": {str(k): v for k, v in by_version.items()},
    }


def rotate_master_key(db: Session, user_id: int | None = None) -> dict:
    """Create a new master key and re-wrap every data key with it. Returns a summary."""
    old_version, _ = active_key(db)
    new_version = (db.scalar(select(func.max(MasterKey.version))) or 0) + 1
    new_key = AESGCM.generate_key(bit_length=256)
    wrapped, nonce = wrap_key(load_master_key(), new_key, _keyring_aad(new_version))

    rewrapped = 0
    items = list(db.scalars(select(Document)).all()) + list(db.scalars(select(DocumentVersion)).all())
    for item in items:
        document_id = item.id if isinstance(item, Document) else item.document_id
        aad = document_aad(document_id, item.version_number)
        data_key = unwrap_key(get_key(db, item.key_version), item.wrapped_key, item.key_nonce, aad)
        item.wrapped_key, item.key_nonce = wrap_key(new_key, data_key, aad)
        item.key_version = new_version
        rewrapped += 1

    now = datetime.now(timezone.utc)
    for row in db.scalars(select(MasterKey).where(MasterKey.active.is_(True))).all():
        row.active = False
        row.retired_at = now
    db.add(MasterKey(version=new_version, wrapped_key=wrapped, nonce=nonce, active=True, created_by=user_id))
    db.commit()  # all or nothing: if anything above failed, nothing was committed
    _cache[new_version] = new_key
    return {"previous_version": old_version, "new_version": new_version, "rewrapped_keys": rewrapped}
