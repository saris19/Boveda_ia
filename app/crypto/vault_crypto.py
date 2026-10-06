"""Envelope encryption with AES-256-GCM.

Each document gets its own random 256-bit data key (DEK). The file is encrypted with the
DEK, and the DEK is in turn encrypted ("wrapped") with the master key (KEK). Only the wrapped
DEK is stored in the database, so a stolen database or storage folder is useless without
the master key. AES-GCM is authenticated: any tampering with the ciphertext is detected.
The document id is used as Associated Data, so a ciphertext cannot be swapped between documents.
"""
from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app import config

KEY_SIZE_BYTES = 32   # AES-256
NONCE_SIZE_BYTES = 12  # recommended size for GCM


class IntegrityError(Exception):
    """Raised when a ciphertext fails authentication (tampered or wrong key)."""


@dataclass
class EncryptedPayload:
    ciphertext: bytes
    data_nonce: bytes
    wrapped_key: bytes
    key_nonce: bytes
    sha256: str


_master_key: bytes | None = None


def load_master_key() -> bytes:
    """Load the KEK from VAULT_MASTER_KEY (base64) or from data/master.key (created if missing)."""
    global _master_key
    if _master_key is not None:
        return _master_key

    env_value = os.getenv("VAULT_MASTER_KEY")
    if env_value:
        key = base64.b64decode(env_value)
    elif config.MASTER_KEY_FILE.exists():
        key = base64.b64decode(config.MASTER_KEY_FILE.read_text().strip())
    else:
        key = AESGCM.generate_key(bit_length=256)
        config.MASTER_KEY_FILE.write_text(base64.b64encode(key).decode())
        try:
            os.chmod(config.MASTER_KEY_FILE, 0o600)
        except OSError:
            pass  # Windows ignores POSIX permissions
        print(f"[Bóveda] Llave maestra nueva generada en {config.MASTER_KEY_FILE}. ¡Guárdala en un lugar seguro!")

    if len(key) != KEY_SIZE_BYTES:
        raise ValueError("La llave maestra debe ser de 32 bytes (AES-256) codificada en base64.")
    _master_key = key
    return key


def encrypt_document(plaintext: bytes, document_id: str) -> EncryptedPayload:
    aad = document_id.encode()
    data_key = AESGCM.generate_key(bit_length=256)

    data_nonce = os.urandom(NONCE_SIZE_BYTES)
    ciphertext = AESGCM(data_key).encrypt(data_nonce, plaintext, aad)

    key_nonce = os.urandom(NONCE_SIZE_BYTES)
    wrapped_key = AESGCM(load_master_key()).encrypt(key_nonce, data_key, aad)

    return EncryptedPayload(
        ciphertext=ciphertext,
        data_nonce=data_nonce,
        wrapped_key=wrapped_key,
        key_nonce=key_nonce,
        sha256=hashlib.sha256(plaintext).hexdigest(),
    )


def decrypt_document(
    ciphertext: bytes, data_nonce: bytes, wrapped_key: bytes, key_nonce: bytes, document_id: str, expected_sha256: str
) -> bytes:
    aad = document_id.encode()
    try:
        data_key = AESGCM(load_master_key()).decrypt(key_nonce, wrapped_key, aad)
        plaintext = AESGCM(data_key).decrypt(data_nonce, ciphertext, aad)
    except InvalidTag as error:
        raise IntegrityError("El documento fue alterado o la llave no corresponde.") from error

    if hashlib.sha256(plaintext).hexdigest() != expected_sha256:
        raise IntegrityError("El hash SHA-256 no coincide con el registrado.")
    return plaintext
