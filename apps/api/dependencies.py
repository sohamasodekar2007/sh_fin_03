"""
Tenant-scoped auth middleware (Days 5-7 task).

`get_current_user` is a FastAPI dependency every protected router requires.
It reads either the `access_token` cookie or the `Authorization: Bearer <token>`
header, validates the JWT, and returns {"user_id": ..., "tenant_id": ...}
so route handlers can scope every DB query to the caller's tenant.
"""

from typing import Annotated, TypedDict
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from apps.api.security import decode_access_token
from apps.api.config import get_settings
from apps.api.db import get_db, mongo_available

_bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(TypedDict):
    user_id: str
    tenant_id: str
    email: str | None
    full_name: str | None


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> AuthenticatedUser:
    settings = get_settings()

    # 1. Try to read the access token from cookies first (used by Next.js frontend)
    token = request.cookies.get("access_token")
    
    # 2. Try the Authorization: Bearer header if the cookie is missing (used by API clients/tests)
    if not token and credentials:
        token = credentials.credentials
        
    if not token:
        if settings.app_env == "development":
            return {
                "user_id": "demo.user",
                "tenant_id": "demo-tenant",
                "email": "demo@cloudcare.ai",
                "full_name": "Demo User",
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing session token or authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    payload = decode_access_token(token)
    if not payload:
        if settings.app_env == "development":
            return {
                "user_id": "demo.user",
                "tenant_id": "demo-tenant",
                "email": "demo@cloudcare.ai",
                "full_name": "Demo User",
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed session token",
        )
        
    # Check database to ensure user still exists. In development, keep the
    # dashboard usable when Mongo is not running; production must still fail
    # closed through the database-backed user check.
    if settings.app_env == "development" and not await mongo_available():
        return {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "email": payload.get("email"),
            "full_name": payload.get("full_name") or payload.get("name"),
        }

    db = get_db()
    try:
        user = await db.users.find_one({"user_id": user_id})
    except Exception as exc:
        if settings.app_env == "development":
            return {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "email": payload.get("email"),
                "full_name": payload.get("full_name") or payload.get("name"),
            }
        raise exc
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
        )
        
    return {
        "user_id": user_id,
        "tenant_id": user.get("tenant_id", tenant_id),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
    }


# Shorthand type alias so routers can write `current_user: CurrentUser`
# instead of repeating the Annotated[...] every time.
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
