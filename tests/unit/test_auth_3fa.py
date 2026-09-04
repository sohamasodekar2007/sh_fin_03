import datetime
import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi.testclient import TestClient
from jose import jwt
from passlib.context import CryptContext

from apps.api.main import app
from apps.api.db import get_db
from apps.api.config import get_settings
from apps.api.routers.auth import pwd_context

# Mock Database setup
mock_db = MagicMock()
app.dependency_overrides[get_db] = lambda: mock_db

# Patch get_db at the module level where they are imported and called directly
patcher_auth = patch("apps.api.routers.auth.get_db", return_value=mock_db)
patcher_dep = patch("apps.api.dependencies.get_db", return_value=mock_db)
patcher_auth.start()
patcher_dep.start()

client = TestClient(app)
settings = get_settings()


@pytest.fixture(autouse=True)
def run_before_and_after_tests():
    # Clear all overrides/mock settings before each test
    mock_db.reset_mock()
    yield


# ---------------------------------------------------------------------------
# Password Authentication Tests (Step 1)
# ---------------------------------------------------------------------------

def test_login_correct_password_requires_otp_for_non_demo_user():
    user_data = {
        "user_id": "real.user",
        "hashed_password": pwd_context.hash("password123"),
        "email": "real.user@example.com",
        "tenant_id": "demo-tenant",
        "failed_login_attempts": 0,
        "otp_bypass_enabled": False,
    }
    
    # Mock database lookup
    mock_db.users.find_one = AsyncMock(return_value=user_data)
    mock_db.sessions.update_one = AsyncMock()
    mock_db.users.update_one = AsyncMock()
    
    # Mock audit log
    mock_db.audit_logs.insert_one = AsyncMock()
    
    with patch("apps.api.routers.auth.send_otp_email_sync") as mock_send_email:
        response = client.post(
            "/v1/auth/login",
            json={"user_id": "real.user", "password": "password123"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "otp_required"
        assert data["user_id"] == "real.user"
        assert "temp_token" in data
        
        # Verify temp token holds the correct claims
        claims = jwt.decode(data["temp_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert claims["sub"] == "real.user"
        assert claims["type"] == "temp_auth"
        assert claims["step"] == "otp"


def test_demo_login_bypasses_otp():
    user_data = {
        "user_id": "demo.user",
        "hashed_password": pwd_context.hash("password123"),
        "email": "demo.user@example.com",
        "tenant_id": "demo-tenant",
        "failed_login_attempts": 0,
        "otp_bypass_enabled": True,
    }

    mock_db.users.find_one = AsyncMock(return_value=user_data)
    mock_db.users.update_one = AsyncMock()
    mock_db.audit_logs.insert_one = AsyncMock()

    response = client.post(
        "/v1/auth/login",
        json={"user_id": "demo.user", "password": "password123"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "authenticated"
    assert data["user_id"] == "demo.user"
    assert data["tenant_id"] == "demo-tenant"
    assert data["access_token"]

    claims = jwt.decode(data["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert claims["sub"] == "demo.user"
    assert claims["type"] == "access"


def test_login_wrong_password():
    user_data = {
        "user_id": "demo.user",
        "hashed_password": pwd_context.hash("password123"),
        "email": "demo.user@example.com",
        "tenant_id": "demo-tenant",
        "failed_login_attempts": 0,
    }
    mock_db.users.find_one = AsyncMock(return_value=user_data)
    mock_db.users.update_one = AsyncMock()
    mock_db.audit_logs.insert_one = AsyncMock()
    
    response = client.post(
        "/v1/auth/login",
        json={"user_id": "demo.user", "password": "wrong_password"}
    )
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid user ID or password"
    mock_db.users.update_one.assert_called()


def test_login_user_lockout():
    now = datetime.datetime.now(datetime.timezone.utc)
    # User is locked out
    user_data = {
        "user_id": "demo.user",
        "hashed_password": pwd_context.hash("password123"),
        "email": "demo.user@example.com",
        "tenant_id": "demo-tenant",
        "locked_until": now + datetime.timedelta(minutes=10)
    }
    mock_db.users.find_one = AsyncMock(return_value=user_data)
    
    response = client.post(
        "/v1/auth/login",
        json={"user_id": "demo.user", "password": "password123"}
    )
    
    assert response.status_code == 429
    assert "locked" in response.json()["detail"]


# ---------------------------------------------------------------------------
# OTP Verification Tests (Step 2)
# ---------------------------------------------------------------------------

def test_verify_otp_correct():
    session_id = str(uuid.uuid4())
    temp_payload = {
        "sub": "demo.user",
        "session_id": session_id,
        "type": "temp_auth",
        "step": "otp",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
    }
    temp_token = jwt.encode(temp_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    session_data = {
        "session_id": session_id,
        "user_id": "demo.user",
        "otp_code": "123456",
        "otp_expires_at": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5),
        "otp_attempts": 0,
    }
    user_data = {
        "user_id": "demo.user",
        "email": "demo.user@example.com",
    }
    
    mock_db.sessions.find_one = AsyncMock(return_value=session_data)
    mock_db.users.find_one = AsyncMock(return_value=user_data)
    mock_db.sessions.update_one = AsyncMock()
    mock_db.webauthn_credentials.find_one = AsyncMock(return_value=None) # No credentials registered yet
    mock_db.audit_logs.insert_one = AsyncMock()
    
    response = client.post(
        "/v1/auth/otp/verify",
        json={"temp_token": temp_token, "otp": "123456"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "webauthn_registration_required"
    assert data["user_id"] == "demo.user"
    assert "temp_token" in data


def test_verify_otp_incorrect():
    session_id = str(uuid.uuid4())
    temp_payload = {
        "sub": "demo.user",
        "session_id": session_id,
        "type": "temp_auth",
        "step": "otp",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
    }
    temp_token = jwt.encode(temp_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    session_data = {
        "session_id": session_id,
        "user_id": "demo.user",
        "otp_code": "123456",
        "otp_expires_at": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5),
        "otp_attempts": 2,
    }
    user_data = {
        "user_id": "demo.user",
    }
    
    mock_db.sessions.find_one = AsyncMock(return_value=session_data)
    mock_db.users.find_one = AsyncMock(return_value=user_data)
    mock_db.sessions.update_one = AsyncMock()
    mock_db.audit_logs.insert_one = MagicMock()
    
    response = client.post(
        "/v1/auth/otp/verify",
        json={"temp_token": temp_token, "otp": "000000"} # wrong otp
    )
    
    assert response.status_code == 400
    assert "Invalid" in response.json()["detail"]
    mock_db.sessions.update_one.assert_called_with(
        {"session_id": session_id},
        {"$inc": {"otp_attempts": 1}}
    )


def test_verify_otp_expired():
    session_id = str(uuid.uuid4())
    temp_payload = {
        "sub": "demo.user",
        "session_id": session_id,
        "type": "temp_auth",
        "step": "otp",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
    }
    temp_token = jwt.encode(temp_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    # OTP expired 1 minute ago
    session_data = {
        "session_id": session_id,
        "user_id": "demo.user",
        "otp_code": "123456",
        "otp_expires_at": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1),
        "otp_attempts": 0,
    }
    user_data = {
        "user_id": "demo.user",
    }
    
    mock_db.sessions.find_one = AsyncMock(return_value=session_data)
    mock_db.users.find_one = AsyncMock(return_value=user_data)
    
    response = client.post(
        "/v1/auth/otp/verify",
        json={"temp_token": temp_token, "otp": "123456"}
    )
    
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# WebAuthn and JWT Tests (Step 3)
# ---------------------------------------------------------------------------

def test_webauthn_bypass():
    session_id = str(uuid.uuid4())
    temp_payload = {
        "sub": "demo.user",
        "session_id": session_id,
        "type": "temp_auth",
        "step": "webauthn",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
    }
    temp_token = jwt.encode(temp_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    session_data = {
        "session_id": session_id,
        "user_id": "demo.user",
        "otp_verified": True,
    }
    user_data = {
        "user_id": "demo.user",
        "tenant_id": "demo-tenant",
    }
    
    mock_db.sessions.find_one = AsyncMock(return_value=session_data)
    mock_db.sessions.delete_one = AsyncMock()
    mock_db.users.find_one = AsyncMock(return_value=user_data)
    mock_db.audit_logs.insert_one = AsyncMock()
    
    response = client.post(
        "/v1/auth/webauthn/bypass",
        json={"temp_token": temp_token}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user_id"] == "demo.user"
    assert data["bypass"] is True
    
    # Check that HTTP-Only cookie was set
    assert "access_token" in response.cookies
    
    # Verify access token JWT
    access_token = data["access_token"]
    claims = jwt.decode(access_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert claims["sub"] == "demo.user"
    assert claims["tenant_id"] == "demo-tenant"
    assert claims["type"] == "access"


def test_get_current_user_profile():
    # Test checking profile details via access token cookie
    user_data = {
        "user_id": "demo.user",
        "email": "demo.user@example.com",
        "tenant_id": "demo-tenant"
    }
    mock_db.users.find_one = AsyncMock(return_value=user_data)
    
    access_payload = {
        "sub": "demo.user",
        "tenant_id": "demo-tenant",
        "type": "access",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=60)
    }
    access_token = jwt.encode(access_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    # Inject token as a cookie
    client.cookies.set("access_token", access_token)
    
    response = client.get("/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "demo.user"
    assert data["email"] == "demo.user@example.com"
    assert data["tenant_id"] == "demo-tenant"


def test_logout():
    mock_db.audit_logs.insert_one = AsyncMock()
    response = client.post("/v1/auth/logout")
    assert response.status_code == 200
    # Cookie should be deleted/cleared
    assert response.cookies.get("access_token") is None
