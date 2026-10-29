import uuid
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import init_db, db_get_user_by_email

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_register_success():
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "securepassword123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == email
    assert data["token_type"] == "bearer"


def test_register_duplicate_email():
    email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
    resp1 = client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        "/api/auth/register",
        json={"email": email, "password": "anotherpassword"},
    )
    assert resp2.status_code == 400
    assert "уже зарегистрирован" in resp2.json()["detail"]


def test_register_invalid_email_and_password():
    # Invalid email
    resp_invalid_email = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "validpassword"},
    )
    assert resp_invalid_email.status_code == 422

    # Short password (< 6 chars)
    resp_short_pwd = client.post(
        "/api/auth/register",
        json={"email": f"good_{uuid.uuid4().hex[:8]}@example.com", "password": "123"},
    )
    assert resp_short_pwd.status_code == 422


def test_login_success_and_failure():
    email = f"login_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "secretpassword"
    client.post("/api/auth/register", json={"email": email, "password": pwd})

    # Successful login
    resp_ok = client.post("/api/auth/login", json={"email": email, "password": pwd})
    assert resp_ok.status_code == 200
    token = resp_ok.json()["access_token"]
    assert token

    # Wrong password
    resp_wrong = client.post("/api/auth/login", json={"email": email, "password": "wrongpassword"})
    assert resp_wrong.status_code == 401

    # Non-existent user
    resp_nonexistent = client.post(
        "/api/auth/login",
        json={"email": f"nobody_{uuid.uuid4().hex[:8]}@example.com", "password": "password"},
    )
    assert resp_nonexistent.status_code == 401


def test_auth_me_profile():
    email = f"profile_{uuid.uuid4().hex[:8]}@example.com"
    resp_reg = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    token = resp_reg.json()["access_token"]

    # Without token
    resp_no_token = client.get("/api/auth/me")
    assert resp_no_token.status_code == 401

    # With valid token
    resp_profile = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp_profile.status_code == 200
    assert resp_profile.json()["email"] == email


def test_forgot_and_reset_password_flow():
    email = f"reset_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "initial_password"})

    # Forgot password
    resp_forgot = client.post("/api/auth/forgot-password", json={"email": email})
    assert resp_forgot.status_code == 200

    user_data = db_get_user_by_email(email)
    code = user_data["reset_code"]
    assert code is not None

    # Reset password with code
    resp_reset = client.post(
        "/api/auth/reset-password",
        json={"email": email, "code": code, "new_password": "brand_new_password"},
    )
    assert resp_reset.status_code == 200

    # Old password no longer works
    assert client.post("/api/auth/login", json={"email": email, "password": "initial_password"}).status_code == 401

    # New password works
    assert client.post("/api/auth/login", json={"email": email, "password": "brand_new_password"}).status_code == 200


def test_user_data_isolation():
    # User 1
    u1_resp = client.post(
        "/api/auth/register",
        json={"email": f"u1_{uuid.uuid4().hex[:8]}@example.com", "password": "password123"},
    )
    t1 = u1_resp.json()["access_token"]

    # User 2
    u2_resp = client.post(
        "/api/auth/register",
        json={"email": f"u2_{uuid.uuid4().hex[:8]}@example.com", "password": "password123"},
    )
    t2 = u2_resp.json()["access_token"]

    # User 1 creates a private task
    secret_title = f"Секретный проект {uuid.uuid4().hex[:6]}"
    create_resp = client.post(
        "/api/events",
        json={
            "type": "task",
            "title": secret_title,
            "date": "2026-11-01",
            "time": "12:00",
        },
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert create_resp.status_code == 201
    event_id = create_resp.json()["id"]

    # User 2 lists events -> should not see User 1's secret project
    u2_list = client.get("/api/events", headers={"Authorization": f"Bearer {t2}"}).json()
    assert not any(e["title"] == secret_title for e in u2_list)

    # User 1 lists events -> should see their secret project
    u1_list = client.get("/api/events", headers={"Authorization": f"Bearer {t1}"}).json()
    assert any(e["id"] == event_id and e["title"] == secret_title for e in u1_list)
