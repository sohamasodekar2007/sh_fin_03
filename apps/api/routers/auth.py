"""
CloudCare Security & QA Module — 3FA Authentication Router.
Wired to MongoDB, supporting Password (bcrypt) -> OTP (Email/console) -> WebAuthn (py_webauthn) -> JWT.
"""

import datetime
import uuid
import secrets
from typing import Literal, Annotated

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Response, Request
from fastapi.security import OAuth2PasswordBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
from webauthn.helpers.parse_authentication_credential_json import parse_authentication_credential_json
from webauthn.helpers.parse_registration_credential_json import parse_registration_credential_json
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    PublicKeyCredentialDescriptor,
)

from apps.api.config import get_settings
from apps.api.db import get_db
from packages.schemas.schemas import (
    LoginRequest,
    LoginBypassRequest,
    LoginResponse,
    LoginStep1Response,
    OtpVerifyRequest,
    OtpVerifyResponse,
    OtpResendRequest,
    SsoCallbackRequest,
    WebAuthnRegisterBeginRequest,
    WebAuthnRegisterFinishRequest,
    WebAuthnAuthenticateBeginRequest,
    WebAuthnAuthenticateFinishRequest,
    WebAuthnSessionRegisterFinishRequest,
    SsoMfaPreferenceRequest,
    RegisterRequest,
    UserPublic,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/login", auto_error=False)


async def ensure_auth_indexes(db) -> None:
    await db.users.create_index("user_id", unique=True, name="user_id_unique")
    await db.users.create_index("email", name="email")
    await db.sessions.create_index("session_id", unique=True, name="session_id_unique")
    await db.sessions.create_index("user_id", unique=True, name="user_id_unique")
    await db.sessions.create_index("otp_expires_at", expireAfterSeconds=600, name="auth_session_ttl")
    await db.webauthn_credentials.create_index("credential_id", unique=True, name="credential_id_unique")
    await db.webauthn_credentials.create_index("user_id", name="user_id")
    await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)], name="user_auth_events")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def ensure_demo_user(db):
    """Seed the default demo user if they don't exist yet."""
    user = await db.users.find_one({"user_id": "demo.user"})
    if not user:
        hashed = pwd_context.hash("password123")
        await db.users.insert_one({
            "user_id": "demo.user",
            "hashed_password": hashed,
            "email": "teamalpha817@gmail.com",
            "tenant_id": "demo-tenant",
            "failed_login_attempts": 0,
            "otp_bypass_enabled": False,
        })
    else:
        updates = {"otp_bypass_enabled": False}
        if user.get("email") != "teamalpha817@gmail.com":
            updates["email"] = "teamalpha817@gmail.com"
        await db.users.update_one({"user_id": "demo.user"}, {"$set": updates})


def _build_access_token(user_id: str, tenant_id: str, settings, now: datetime.datetime) -> str:
    access_token_payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "type": "access",
        "exp": now + datetime.timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(access_token_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _set_access_token_cookie(response: Response, access_token: str, settings) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="none" if settings.app_env != "development" else "lax",
        max_age=settings.jwt_expire_minutes * 60,
    )


def _webauthn_expected_origins(settings) -> list[str]:
    origins = [settings.webauthn_origin, *settings.cors_origin_list]
    return list(dict.fromkeys(origin for origin in origins if origin))


async def _verify_password_login(db, user_id: str, password: str, now: datetime.datetime):
    await ensure_demo_user(db)

    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID or password",
        )

    locked_until = user.get("locked_until")
    if locked_until:
        if isinstance(locked_until, str):
            locked_until = datetime.datetime.fromisoformat(locked_until)
        if locked_until > now:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account temporarily locked due to too many failed attempts. Try again later.",
            )

    if not user.get("hashed_password") or not pwd_context.verify(password, user["hashed_password"]):
        attempts = user.get("failed_login_attempts", 0) + 1
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"failed_login_attempts": attempts}}
        )
        await log_auth_event(db, user_id, "login.password_failure", {"attempts": attempts})

        if attempts >= 5:
            locked_until_time = now + datetime.timedelta(minutes=15)
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"locked_until": locked_until_time}}
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed attempts. Account locked for 15 minutes.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID or password",
        )

    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"failed_login_attempts": 0}, "$unset": {"locked_until": ""}}
    )
    return user


async def log_auth_event(db, user_id: str, event_type: str, details: dict):
    """Log security events to stdout and store in MongoDB audit_logs collection."""
    now = datetime.datetime.now(datetime.timezone.utc)
    print(f"[AUDIT LOG] {now.isoformat()} - User: {user_id} - Event: {event_type} - Details: {details}")
    try:
        await db.audit_logs.insert_one({
            "user_id": user_id,
            "event_type": event_type,
            "details": details,
            "timestamp": now
        })
    except Exception as e:
        print(f"Failed to write audit log: {e}")


def send_otp_email_sync(to_email: str, otp: str, settings):
    """Builds the OTP HTML, then hands off to the shared transport
    (services/notifications/email.py — Brevo -> Resend -> SMTP), extracted
    in Phase 5 so the Supervisor approval email reuses the same delivery
    chain instead of duplicating it."""
    print(f"==================================================")
    print(f"OTP Email to {to_email}: Your CloudCare OTP is {otp}")
    print(f"==================================================")
    print(f"DEBUG: brevo_api_key present = {bool(settings.brevo_api_key)}, resend_api_key present = {bool(settings.resend_api_key)}")

    html = f"""
    <html>
      <body style="font-family: sans-serif; padding: 20px; color: #10222E; background-color: #F7FAF9;">
        <div style="max-width: 480px; margin: 0 auto; background: #FFFFFF; border: 1px solid #E4EBE8; border-radius: 8px; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
          <h2 style="margin-top: 0; color: #2F6690;">CloudCare Verification</h2>
          <p>Your one-time verification code is:</p>
          <div style="font-size: 32px; font-weight: bold; letter-spacing: 4px; padding: 15px; background: #E4EBE8; border-radius: 6px; text-align: center; margin: 20px 0;">
            {otp}
          </div>
          <p style="font-size: 13px; color: #627785;">This code will expire in 5 minutes. If you did not request this code, please ignore this email.</p>
        </div>
      </body>
    </html>
    """

    from services.notifications.email import send_email_sync

    send_email_sync(to_email, "CloudCare — Your Verification Code", html, settings)


# ---------------------------------------------------------------------------
# Auth Dependency
# ---------------------------------------------------------------------------

from apps.api.dependencies import get_current_user, CurrentUser


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginStep1Response)
async def login(
    payload: LoginRequest,
    background_tasks: BackgroundTasks,
    response: Response,
) -> LoginStep1Response:
    """Step 1: Password authentication. Triggers OTP send."""
    db = get_db()
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)

    user = await _verify_password_login(db, payload.user_id, payload.password, now)

    if settings.app_env == "development" and payload.user_id == "demo.user" and user.get("otp_bypass_enabled", False):
        tenant_id = user.get("tenant_id", "demo-tenant")
        access_token = _build_access_token(payload.user_id, tenant_id, settings, now)
        _set_access_token_cookie(response, access_token, settings)
        await log_auth_event(db, payload.user_id, "login.demo_bypass_success", {})
        return LoginStep1Response(
            status="authenticated",
            user_id=payload.user_id,
            access_token=access_token,
            tenant_id=tenant_id,
        )
    
    # Check rate limit on OTP generation (max 1 OTP per 60 seconds)
    last_otp_sent = user.get("last_otp_sent")
    if last_otp_sent:
        if isinstance(last_otp_sent, str):
            last_otp_sent = datetime.datetime.fromisoformat(last_otp_sent)
        if (now - last_otp_sent).total_seconds() < 60:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait 60 seconds before requesting another verification code.",
            )
            
    # Secure OTP generation
    otp = "".join(secrets.choice("0123456789") for _ in range(6))
    otp_expires_at = now + datetime.timedelta(minutes=5)
    
    session_id = str(uuid.uuid4())
    await db.sessions.update_one(
        {"user_id": payload.user_id},
        {
            "$set": {
                "session_id": session_id,
                "otp_code": otp,
                "otp_expires_at": otp_expires_at,
                "otp_attempts": 0,
                "otp_verified": False,
                "updated_at": now
            }
        },
        upsert=True
    )
    
    await db.users.update_one(
        {"user_id": payload.user_id},
        {"$set": {"last_otp_sent": now}}
    )
    
    # Send email in background
    background_tasks.add_task(send_otp_email_sync, user["email"], otp, settings)
    await log_auth_event(db, payload.user_id, "otp.sent", {"expires_at": otp_expires_at.isoformat()})
    
    # Issue short-lived temp token
    temp_payload = {
        "sub": payload.user_id,
        "session_id": session_id,
        "type": "temp_auth",
        "step": "otp",
        "exp": now + datetime.timedelta(minutes=10)
    }
    temp_token = jwt.encode(temp_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    return LoginStep1Response(
        status="otp_required",
        user_id=payload.user_id,
        temp_token=temp_token
    )


@router.post("/login/bypass", response_model=LoginResponse)
async def login_bypass(payload: LoginBypassRequest, response: Response) -> LoginResponse:
    """Development/demo login that verifies password but skips OTP and WebAuthn."""
    db = get_db()
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)

    if settings.app_env != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Login bypass is only available in development.",
        )

    user = await _verify_password_login(db, payload.user_id, payload.password, now)
    bypass_allowed = payload.user_id == "demo.user" or user.get("otp_bypass_enabled", False)
    if not bypass_allowed:
        await log_auth_event(db, payload.user_id, "login.bypass_denied", {"reason": "disabled_for_user"})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Login bypass is not enabled for this user.",
        )

    tenant_id = user.get("tenant_id", "demo-tenant")
    access_token = _build_access_token(payload.user_id, tenant_id, settings, now)
    _set_access_token_cookie(response, access_token, settings)
    await log_auth_event(db, payload.user_id, "login.bypass_success", {})
    return LoginResponse(access_token=access_token, user_id=payload.user_id, tenant_id=tenant_id)


@router.post("/otp/verify", response_model=OtpVerifyResponse)
async def verify_otp(payload: OtpVerifyRequest) -> OtpVerifyResponse:
    """Step 2: Verify OTP. Returns whether WebAuthn registration or authentication is required."""
    db = get_db()
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    
    try:
        token_data = jwt.decode(payload.temp_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = token_data.get("sub")
        session_id = token_data.get("session_id")
        token_type = token_data.get("type")
        step = token_data.get("step")
        if token_type != "temp_auth" or step != "otp" or not user_id or not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid temporary authentication token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired temporary authentication token",
        )
        
    session = await db.sessions.find_one({"session_id": session_id, "user_id": user_id})
    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session not found or expired",
        )
        
    # Check lockout
    user = await db.users.find_one({"user_id": user_id})
    locked_until = user.get("locked_until")
    if locked_until:
        if isinstance(locked_until, str):
            locked_until = datetime.datetime.fromisoformat(locked_until)
        if locked_until > now:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account temporarily locked. Try again later.",
            )
            
    # Check OTP expiration
    otp_expires_at = session.get("otp_expires_at")
    if isinstance(otp_expires_at, str):
        otp_expires_at = datetime.datetime.fromisoformat(otp_expires_at)
    if otp_expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please request a new one.",
        )
        
    # Check attempts
    attempts = session.get("otp_attempts", 0)
    if attempts >= 5:
        locked_until_time = now + datetime.timedelta(minutes=15)
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"locked_until": locked_until_time}}
        )
        await log_auth_event(db, user_id, "otp.lockout", {"attempts": attempts})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed verification attempts. Account locked for 15 minutes.",
        )
        
    # Verify OTP
    if session.get("otp_code") != payload.otp:
        await db.sessions.update_one(
            {"session_id": session_id},
            {"$inc": {"otp_attempts": 1}}
        )
        await log_auth_event(db, user_id, "otp.verified_failure", {"attempts": attempts + 1})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code",
        )
        
    # Success
    await db.sessions.update_one(
        {"session_id": session_id},
        {"$set": {"otp_verified": True}, "$unset": {"otp_code": ""}}
    )
    await log_auth_event(db, user_id, "otp.verified_success", {})
    
    # Check WebAuthn status
    credential = await db.webauthn_credentials.find_one({"user_id": user_id})
    status_str = "webauthn_required" if credential else "webauthn_registration_required"
    
    # Issue a new temp_token for the WebAuthn phase
    temp_payload = {
        "sub": user_id,
        "session_id": session_id,
        "type": "temp_auth",
        "step": "webauthn",
        "exp": now + datetime.timedelta(minutes=10)
    }
    new_temp_token = jwt.encode(temp_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    return OtpVerifyResponse(
        status=status_str,
        user_id=user_id,
        temp_token=new_temp_token
    )


@router.post("/otp/resend")
async def resend_otp(payload: OtpResendRequest, background_tasks: BackgroundTasks):
    """Resend a new OTP if rate limits allow."""
    db = get_db()
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    
    try:
        token_data = jwt.decode(payload.temp_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = token_data.get("sub")
        session_id = token_data.get("session_id")
        token_type = token_data.get("type")
        step = token_data.get("step")
        if token_type != "temp_auth" or step != "otp" or not user_id or not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid temporary authentication token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired temporary authentication token",
        )
        
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Check rate limit (60 seconds)
    last_otp_sent = user.get("last_otp_sent")
    if last_otp_sent:
        if isinstance(last_otp_sent, str):
            last_otp_sent = datetime.datetime.fromisoformat(last_otp_sent)
        if (now - last_otp_sent).total_seconds() < 60:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait 60 seconds before requesting another verification code.",
            )
            
    # Generate new OTP
    otp = "".join(secrets.choice("0123456789") for _ in range(6))
    otp_expires_at = now + datetime.timedelta(minutes=5)
    
    await db.sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "otp_code": otp,
                "otp_expires_at": otp_expires_at,
                "otp_attempts": 0,
                "updated_at": now
            }
        }
    )
    
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"last_otp_sent": now}}
    )
    
    background_tasks.add_task(send_otp_email_sync, user["email"], otp, settings)
    await log_auth_event(db, user_id, "otp.resend", {"expires_at": otp_expires_at.isoformat()})
    return {"message": "Verification code resent"}


@router.post("/webauthn/register/begin")
async def register_begin(payload: WebAuthnRegisterBeginRequest):
    """Generate options for WebAuthn credential registration."""
    db = get_db()
    settings = get_settings()
    
    try:
        token_data = jwt.decode(payload.temp_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = token_data.get("sub")
        session_id = token_data.get("session_id")
        token_type = token_data.get("type")
        step = token_data.get("step")
        if token_type != "temp_auth" or step != "webauthn" or not user_id or not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid temporary authentication token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired temporary authentication token",
        )
        
    session = await db.sessions.find_one({"session_id": session_id, "user_id": user_id})
    if not session or not session.get("otp_verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP verification must be completed first",
        )
        
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user_id.encode("utf-8"),
        user_name=user_id,
        user_display_name=user_id,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED
        ),
    )
    
    challenge_str = bytes_to_base64url(options.challenge)
    await db.sessions.update_one(
        {"session_id": session_id},
        {"$set": {"webauthn_challenge": challenge_str}}
    )
    
    await log_auth_event(db, user_id, "webauthn.register_begin", {})
    import json
    return json.loads(options_to_json(options))


@router.post("/webauthn/register/finish")
async def register_finish(payload: WebAuthnRegisterFinishRequest, response: Response):
    """Verify WebAuthn credential registration response. Stores credential and issues access token."""
    db = get_db()
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    
    try:
        token_data = jwt.decode(payload.temp_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = token_data.get("sub")
        session_id = token_data.get("session_id")
        token_type = token_data.get("type")
        step = token_data.get("step")
        if token_type != "temp_auth" or step != "webauthn" or not user_id or not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid temporary authentication token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired temporary authentication token",
        )
        
    session = await db.sessions.find_one({"session_id": session_id, "user_id": user_id})
    if not session or not session.get("webauthn_challenge"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration has not been initiated",
        )
        
    expected_challenge = base64url_to_bytes(session["webauthn_challenge"])
    
    try:
        credential = parse_registration_credential_json(payload.registration_response)
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_origin=_webauthn_expected_origins(settings),
            expected_rp_id=settings.webauthn_rp_id,
            require_user_verification=True,
        )
    except Exception as e:
        expected_origins = _webauthn_expected_origins(settings)
        await log_auth_event(
            db,
            user_id,
            "webauthn.register_finish_failure",
            {"error": str(e), "expected_origins": expected_origins},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"WebAuthn registration verification failed: {e}. Expected origins: {expected_origins}",
        )
        
    cred_id_str = bytes_to_base64url(verification.credential_id)
    pub_key_str = bytes_to_base64url(verification.credential_public_key)
    
    await db.webauthn_credentials.update_one(
        {"credential_id": cred_id_str},
        {
            "$set": {
                "user_id": user_id,
                "public_key": pub_key_str,
                "sign_counter": verification.sign_counter,
                "created_at": now
            }
        },
        upsert=True
    )
    
    await db.sessions.delete_one({"session_id": session_id})
    await log_auth_event(db, user_id, "webauthn.register_finish_success", {"credential_id": cred_id_str})
    
    user = await db.users.find_one({"user_id": user_id})
    access_token_payload = {
        "sub": user_id,
        "tenant_id": user.get("tenant_id", "demo-tenant"),
        "type": "access",
        "exp": now + datetime.timedelta(minutes=settings.jwt_expire_minutes)
    }
    access_token = jwt.encode(access_token_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="none" if settings.app_env != "development" else "lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user_id
    }


@router.post("/webauthn/authenticate/begin")
async def authenticate_begin(payload: WebAuthnAuthenticateBeginRequest):
    """Generate options for WebAuthn authentication."""
    db = get_db()
    settings = get_settings()
    
    try:
        token_data = jwt.decode(payload.temp_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = token_data.get("sub")
        session_id = token_data.get("session_id")
        token_type = token_data.get("type")
        step = token_data.get("step")
        if token_type != "temp_auth" or step != "webauthn" or not user_id or not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid temporary authentication token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired temporary authentication token",
        )
        
    session = await db.sessions.find_one({"session_id": session_id, "user_id": user_id})
    if not session or not session.get("otp_verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP verification must be completed first",
        )
        
    cursor = db.webauthn_credentials.find({"user_id": user_id})
    credentials = await cursor.to_list(length=100)
    
    allow_credentials = []
    for cred in credentials:
        allow_credentials.append(
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(cred["credential_id"])
            )
        )
        
    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED
    )
    
    challenge_str = bytes_to_base64url(options.challenge)
    await db.sessions.update_one(
        {"session_id": session_id},
        {"$set": {"webauthn_challenge": challenge_str}}
    )
    
    await log_auth_event(db, user_id, "webauthn.auth_begin", {})
    import json
    return json.loads(options_to_json(options))


@router.post("/webauthn/authenticate/finish")
async def authenticate_finish(payload: WebAuthnAuthenticateFinishRequest, response: Response):
    """Verify WebAuthn authentication response. Validates sign counter and issues access token."""
    db = get_db()
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    
    try:
        token_data = jwt.decode(payload.temp_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = token_data.get("sub")
        session_id = token_data.get("session_id")
        token_type = token_data.get("type")
        step = token_data.get("step")
        if token_type != "temp_auth" or step != "webauthn" or not user_id or not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid temporary authentication token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired temporary authentication token",
        )
        
    session = await db.sessions.find_one({"session_id": session_id, "user_id": user_id})
    if not session or not session.get("webauthn_challenge"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication has not been initiated",
        )
        
    expected_challenge = base64url_to_bytes(session["webauthn_challenge"])
    
    try:
        credential = parse_authentication_credential_json(payload.authentication_response)
        
        cred_id_str = bytes_to_base64url(credential.raw_id)
        db_credential = await db.webauthn_credentials.find_one({"credential_id": cred_id_str, "user_id": user_id})
        if not db_credential:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="WebAuthn credential not found for this user",
            )
            
        public_key = base64url_to_bytes(db_credential["public_key"])
        current_sign_counter = db_credential["sign_counter"]
        
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=_webauthn_expected_origins(settings),
            credential_public_key=public_key,
            credential_current_sign_counter=current_sign_counter,
            require_user_verification=True,
        )
    except Exception as e:
        await log_auth_event(db, user_id, "webauthn.auth_finish_failure", {"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"WebAuthn authentication failed: {e}",
        )
        
    # Replay Protection: verification.new_sign_counter must exceed database count (or be 0 if not supported/provided)
    if verification.new_sign_counter > 0 and verification.new_sign_counter <= current_sign_counter:
        await log_auth_event(db, user_id, "webauthn.auth_replay_detected", {"credential_id": cred_id_str})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Replay protection trigger: sign counter decreased or stayed identical.",
        )
        
    await db.webauthn_credentials.update_one(
        {"credential_id": cred_id_str},
        {"$set": {"sign_counter": verification.new_sign_counter}}
    )
    
    await db.sessions.delete_one({"session_id": session_id})
    await log_auth_event(db, user_id, "webauthn.auth_finish_success", {"credential_id": cred_id_str})
    
    user = await db.users.find_one({"user_id": user_id})
    access_token_payload = {
        "sub": user_id,
        "tenant_id": user.get("tenant_id", "demo-tenant"),
        "type": "access",
        "exp": now + datetime.timedelta(minutes=settings.jwt_expire_minutes)
    }
    access_token = jwt.encode(access_token_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="none" if settings.app_env != "development" else "lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user_id
    }


@router.post("/webauthn/bypass")
async def webauthn_bypass(payload: WebAuthnRegisterBeginRequest, response: Response):
    """Developer/demo bypass for WebAuthn in case platform authenticators are missing."""
    db = get_db()
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)

    if settings.app_env != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="WebAuthn bypass is only available in development.",
        )
    
    try:
        token_data = jwt.decode(payload.temp_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = token_data.get("sub")
        session_id = token_data.get("session_id")
        token_type = token_data.get("type")
        step = token_data.get("step")
        if token_type != "temp_auth" or step != "webauthn" or not user_id or not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid temporary authentication token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired temporary authentication token",
        )
        
    session = await db.sessions.find_one({"session_id": session_id, "user_id": user_id})
    if not session or not session.get("otp_verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP verification must be completed first",
        )
        
    await db.sessions.delete_one({"session_id": session_id})
    await log_auth_event(db, user_id, "webauthn.bypass_used", {})
    
    user = await db.users.find_one({"user_id": user_id})
    access_token_payload = {
        "sub": user_id,
        "tenant_id": user.get("tenant_id", "demo-tenant"),
        "type": "access",
        "exp": now + datetime.timedelta(minutes=settings.jwt_expire_minutes)
    }
    access_token = jwt.encode(access_token_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="none" if settings.app_env != "development" else "lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user_id,
        "bypass": True
    }


@router.post("/logout")
async def logout(response: Response, request: Request):
    """Log out user, clearing access token cookie."""
    db = get_db()
    settings = get_settings()
    
    # Try retrieving user_id for audit logging
    user_id = "unknown"
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            user_id = payload.get("sub", "unknown")
        except Exception:
            pass
            
    response.delete_cookie(
        "access_token",
        secure=settings.app_env != "development",
        samesite="none" if settings.app_env != "development" else "lax"
    )
    await log_auth_event(db, user_id, "logout", {})
    return {"message": "Successfully logged out"}


@router.post("/register", response_model=UserPublic, status_code=201)
async def register(payload: RegisterRequest) -> UserPublic:
    """Register a new user account with Password/Email (pre-enrollment for 3FA)."""
    db = get_db()
    
    # Check if user already exists
    existing_user = await db.users.find_one({"user_id": payload.user_id})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID is already registered.",
        )
        
    # Check if email is already used
    existing_email = await db.users.find_one({"email": payload.email})
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address is already in use.",
        )
        
    # Hash password and store user
    hashed = pwd_context.hash(payload.password)
    await db.users.insert_one({
        "user_id": payload.user_id,
        "hashed_password": hashed,
        "email": payload.email,
        "tenant_id": payload.tenant_id,
        "full_name": payload.full_name,
        "failed_login_attempts": 0,
    })
    
    await log_auth_event(db, payload.user_id, "register.success", {"email": payload.email})
    return UserPublic(
        user_id=payload.user_id,
        tenant_id=payload.tenant_id,
        email=payload.email,
        full_name=payload.full_name,
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh(response: Response, request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(oauth2_scheme)] = None) -> LoginResponse:
    """
    Exchange a token for a fresh one with a new expiry, without re-sending
    the password. Accepts cookies or Bearer headers.
    """
    settings = get_settings()
    token = request.cookies.get("access_token")
    if not token and credentials:
        token = credentials.credentials
        
    if not token:
        raise HTTPException(status_code=401, detail="No session token found")
        
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token — please log in again")
        
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if not user_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid token claims")
        
    now = datetime.datetime.now(datetime.timezone.utc)
    access_token_payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "type": "access",
        "exp": now + datetime.timedelta(minutes=settings.jwt_expire_minutes)
    }
    new_token = jwt.encode(access_token_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    response.set_cookie(
        key="access_token",
        value=new_token,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    
    return LoginResponse(access_token=new_token, user_id=user_id, tenant_id=tenant_id)


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: CurrentUser) -> UserPublic:
    """Retrieve details of the currently authenticated user."""
    return UserPublic(
        user_id=current_user["user_id"],
        tenant_id=current_user["tenant_id"],
        email=current_user.get("email"),
        full_name=current_user.get("full_name"),
    )


@router.post("/sso/mfa-preference")
async def set_sso_mfa_preference(
    payload: SsoMfaPreferenceRequest,
    current_user: CurrentUser,
):
    db = get_db()
    now = datetime.datetime.now(datetime.timezone.utc)
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"sso_mfa_level": payload.mfa_level, "sso_mfa_updated_at": now}},
    )
    await log_auth_event(db, current_user["user_id"], "sso.mfa_preference_set", {"mfa_level": payload.mfa_level})
    return {"mfa_level": payload.mfa_level}


@router.post("/webauthn/session/register/begin")
async def session_register_begin(current_user: CurrentUser):
    """Start passkey enrollment from an already-authenticated SSO session."""
    db = get_db()
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    user_id = current_user["user_id"]

    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user_id.encode("utf-8"),
        user_name=user_id,
        user_display_name=current_user.get("full_name") or user_id,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED
        ),
    )

    session_id = str(uuid.uuid4())
    await db.sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "session_id": session_id,
                "user_id": user_id,
                "otp_verified": True,
                "webauthn_challenge": bytes_to_base64url(options.challenge),
                "otp_expires_at": now + datetime.timedelta(minutes=10),
                "updated_at": now,
                "purpose": "sso_webauthn_enrollment",
            }
        },
        upsert=True,
    )

    await log_auth_event(db, user_id, "sso.webauthn_register_begin", {})
    import json
    options_payload = json.loads(options_to_json(options))
    options_payload["session_id"] = session_id
    return options_payload


@router.post("/webauthn/session/register/finish")
async def session_register_finish(
    payload: WebAuthnSessionRegisterFinishRequest,
    current_user: CurrentUser,
):
    """Finish passkey enrollment from an already-authenticated SSO session."""
    db = get_db()
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)
    user_id = current_user["user_id"]

    session = await db.sessions.find_one({
        "session_id": payload.session_id,
        "user_id": user_id,
        "purpose": "sso_webauthn_enrollment",
    })
    if not session or not session.get("webauthn_challenge"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passkey enrollment has not been initiated.",
        )

    try:
        credential = parse_registration_credential_json(payload.registration_response)
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(session["webauthn_challenge"]),
            expected_origin=_webauthn_expected_origins(settings),
            expected_rp_id=settings.webauthn_rp_id,
            require_user_verification=True,
        )
    except Exception as e:
        expected_origins = _webauthn_expected_origins(settings)
        await log_auth_event(
            db,
            user_id,
            "sso.webauthn_register_finish_failure",
            {"error": str(e), "expected_origins": expected_origins},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"WebAuthn registration verification failed: {e}. Expected origins: {expected_origins}",
        )

    cred_id_str = bytes_to_base64url(verification.credential_id)
    pub_key_str = bytes_to_base64url(verification.credential_public_key)
    await db.webauthn_credentials.update_one(
        {"credential_id": cred_id_str},
        {
            "$set": {
                "user_id": user_id,
                "public_key": pub_key_str,
                "sign_counter": verification.sign_counter,
                "created_at": now,
            }
        },
        upsert=True,
    )
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"sso_mfa_level": "3fa", "sso_mfa_updated_at": now}},
    )
    await db.sessions.delete_one({"session_id": payload.session_id})
    await log_auth_event(db, user_id, "sso.webauthn_register_finish_success", {"credential_id": cred_id_str})
    return {"mfa_level": "3fa", "credential_id": cred_id_str}


@router.post("/sso-callback", response_model=LoginStep1Response)
async def sso_callback(payload: SsoCallbackRequest, response: Response) -> LoginStep1Response:
    """
    Phase 9 — called server-side by the frontend's NextAuth v5 config
    (src/auth.ts's jwt callback) right after Google/GitHub completes the
    OAuth handshake, with the verified profile it received from the
    provider. Creates or links the CloudCare user by provider+provider
    account id (falling back to linking an existing password account by
    email), then returns the SAME LoginStep1Response shape password login
    does on success — one JWT shape, one auth model, regardless of path.

    Password + OTP's existing two-factor flow (login -> otp/verify) and
    the WebAuthn endpoints below are untouched by this addition; this is a
    third, independent way to reach the same access_token issuance the
    other two flows already use (_build_access_token / _set_access_token_cookie).
    """
    db = get_db()
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)

    user = await db.users.find_one(
        {"sso_provider": payload.provider, "sso_provider_account_id": payload.provider_account_id}
    )

    if not user:
        # Link into an existing password account with the same email,
        # rather than creating a second, disconnected identity for it.
        user = await db.users.find_one({"email": payload.email})
        if user:
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"sso_provider": payload.provider, "sso_provider_account_id": payload.provider_account_id}},
            )
        else:
            new_user_id = f"{payload.provider}:{payload.provider_account_id}"
            user = {
                "user_id": new_user_id,
                "email": payload.email,
                "full_name": payload.name,
                "tenant_id": "demo-tenant",
                "sso_provider": payload.provider,
                "sso_provider_account_id": payload.provider_account_id,
                "hashed_password": None,
                "failed_login_attempts": 0,
            }
            await db.users.insert_one(user)
            await log_auth_event(db, new_user_id, "sso.user_created", {"provider": payload.provider})

    user_id = user["user_id"]
    tenant_id = user.get("tenant_id", "demo-tenant")

    access_token = _build_access_token(user_id, tenant_id, settings, now)
    _set_access_token_cookie(response, access_token, settings)
    await log_auth_event(db, user_id, "sso.login_success", {"provider": payload.provider})

    return LoginStep1Response(
        status="authenticated",
        user_id=user_id,
        access_token=access_token,
        tenant_id=tenant_id,
    )
