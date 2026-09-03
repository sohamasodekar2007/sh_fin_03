"""
Auth dependency chain: Bearer token -> decoded NextAuth JWT -> auto-
provisioned Mongo user (spec section 2, "Auto-Provisioning System").

If a valid JWT contains an email that doesn't exist in the `users`
collection yet, get_current_user silently provisions it from the JWT's own
claims (provider + provider_account_id / google_sub / github id / entra
oid) before returning — so a first-time Google/GitHub/Entra sign-in never
needs a separate "create account" round trip.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.db import get_db
from apps.api.security import decode_nextauth_jwt
from packages.schemas.schemas import UserInDB

_bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> UserInDB:
    claims = decode_nextauth_jwt(credentials.credentials)
    if claims is None or not claims.get("email"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session token.")

    db = get_db()
    email = claims["email"]
    existing = await db.users.find_one({"email": email})
    if existing:
        existing.pop("_id", None)
        return UserInDB.model_validate(existing)

    user = UserInDB(
        tenant_id="demo-tenant",
        email=email,
        full_name=claims.get("name"),
        image=claims.get("picture"),
        provider=claims.get("provider", "credentials"),
        provider_account_id=claims.get("provider_account_id") or claims.get("sub"),
    )
    await db.users.insert_one(user.model_dump())
    return user


async def get_tenant_id(user: UserInDB = Depends(get_current_user)) -> str:
    return user.tenant_id
