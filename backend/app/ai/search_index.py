"""Blind index for searching inside encrypted documents without storing their text.

At upload time every relevant word of the document is normalized (lowercase, no accents, light Spanish
stemming) and transformed with HMAC-SHA256 using a key derived from the master key. Only these
opaque tokens are stored. At search time the query words go through the same transformation, so the
server can tell which documents contain a word without ever keeping the plaintext.

Trade-off (documented on purpose): equal words produce equal tokens, so someone with database access
could see that two documents share a word, but not which word without the key.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from functools import lru_cache

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.ai.classifier import SPANISH_STOPWORDS, normalize_text
from app.crypto.vault_crypto import load_master_key

TOKEN_HEX_LENGTH = 16          # 64 bits per token: plenty to avoid collisions in a document vault
MAX_TOKENS_PER_DOCUMENT = 4000
WORD_PATTERN = re.compile(r"[a-zñ]{3,}")
VOWELS = "aeiou"


def stem(word: str) -> str:
    """Very light Spanish stemmer so that 'facturas', 'factura' and 'facturación' share a root when possible."""
    for suffix in ("aciones", "acion", "amientos", "amiento", "mente"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    if word.endswith("es") and len(word) > 5:
        word = word[:-2]
    elif word.endswith("s") and len(word) > 4:
        word = word[:-1]
    if len(word) > 4 and word[-1] in VOWELS:
        word = word[:-1]
    return word


def extract_stems(text: str) -> list[str]:
    """Unique stems of the meaningful words of a text, in order of appearance."""
    words = WORD_PATTERN.findall(normalize_text(text))
    stems = (stem(word) for word in words if word not in SPANISH_STOPWORDS)
    return list(dict.fromkeys(s for s in stems if len(s) >= 3))


@lru_cache(maxsize=1)
def _index_key() -> bytes:
    # A separate key derived from the master key: the encryption key itself is never reused for indexing.
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"boveda-ia/blind-index/v1").derive(
        load_master_key()
    )


def blind_token(stem_value: str) -> str:
    digest = hmac.new(_index_key(), stem_value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:TOKEN_HEX_LENGTH]


def build_blind_index(text: str) -> list[str]:
    tokens = {blind_token(s) for s in extract_stems(text)}
    return sorted(tokens)[:MAX_TOKENS_PER_DOCUMENT]
