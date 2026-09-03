"""
AES-256-GCM encryption for cloud credentials at rest (spec section 3).

Every CloudAccount's secret (GCP service-account JSON, Azure client secret,
on-prem SSH key — AWS instead uses a customer-owned IAM role + external ID,
so it never holds a long-lived secret at all) is encrypted with this module
before it's written to Mongo, and decrypted only in-process, only for the
duration of an adapter call.

Ciphertext layout stored in CloudAccount.encrypted_credentials:
    base64( 12-byte nonce || AESGCM ciphertext-with-tag )
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apps.api.config import get_settings

_NONCE_LEN = 12


def _key() -> bytes:
    settings = get_settings()
    key = base64.b64decode(settings.encryption_key)
    if len(key) != 32:
        raise RuntimeError(
            "ENCRYPTION_KEY must decode to exactly 32 bytes for AES-256-GCM. "
            "Generate one with: python -c \"import os,base64;print(base64.b64encode(os.urandom(32)).decode())\""
        )
    return key


def encrypt_credentials(plaintext: str) -> str:
    aesgcm = AESGCM(_key())
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_credentials(encrypted: str) -> str:
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    aesgcm = AESGCM(_key())
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    return plaintext.decode("utf-8")
