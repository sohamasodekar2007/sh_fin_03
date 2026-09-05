"""
Password hashing + JWT helpers.

Replaces the old auth.py placeholder comment block — this is the real
implementation: bcrypt for password storage, python-jose for signed,
expiring JWTs. Nothing here talks to MongoDB; routers own the DB calls.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from apps.api.config import get_settings


class BcryptPasswordContext:
    """Small bcrypt wrapper compatible with bcrypt 5.x.

    passlib's bcrypt handler currently relies on backend internals that were
    removed in newer bcrypt releases, which breaks hashing at runtime on this
    environment. Keep the same .hash/.verify surface used by the routers/tests.
    """

    @staticmethod
    def hash(plain_password: str) -> str:
        password_bytes = plain_password.encode("utf-8")
        if len(password_bytes) > 72:
            raise ValueError("bcrypt passwords must be 72 bytes or fewer")
        return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify(plain_password: str, hashed_password: str) -> bool:
        password_bytes = plain_password.encode("utf-8")
        if len(password_bytes) > 72:
            return False
        try:
            return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
        except (TypeError, ValueError):
            return False


pwd_context = BcryptPasswordContext()


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, tenant_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "tenant_id": tenant_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    """Returns the decoded payload, or None if the token is invalid/expired."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        return None


def decode_access_token_allow_expired(token: str) -> dict | None:
    """Same as decode_access_token, but ignores expiry — used only by the
    /v1/auth/refresh endpoint so a *recently* expired token can still be
    exchanged for a new one, without accepting a forged/tampered token."""
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
    except JWTError:
        return None
