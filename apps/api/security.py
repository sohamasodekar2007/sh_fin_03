"""
FastAPI as a trusting resource server (spec section 2).

FastAPI never mints a JWT and never sees a password — NextAuth is the sole
identity authority. This module only decodes and validates the HS256 JWT
NextAuth signs with NEXTAUTH_SECRET (duplicated into this service's .env),
matching the `jwt` callback shape NextAuth produces by default: `sub`
(user id), `email`, `name`, `picture`, and whatever custom claims
apps/web/lib/auth.ts adds (`provider`, `provider_account_id`).
"""

from __future__ import annotations

from jose import JWTError, jwt

from apps.api.config import get_settings


def decode_nextauth_jwt(token: str) -> dict | None:
    """Returns the decoded claims, or None if the token is invalid/expired/
    signed with the wrong secret."""
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.nextauth_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
    except JWTError:
        return None
