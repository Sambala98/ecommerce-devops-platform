from sqlalchemy import select

from app.models.user import User
from app.security.jwt import decode_access_token
from app.security.password import verify_password


PASSWORD = "StrongTestPassword123!"


def register_payload(
    email: str = "auth-user@example.com",
):
    return {
        "email": email,
        "name": "Auth Test User",
        "password": PASSWORD,
    }


def test_register_user_success(
    client,
    database_session,
):
    response = client.post(
        "/auth/register",
        json=register_payload(),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == "auth-user@example.com"
    assert data["name"] == "Auth Test User"
    assert data["role"] == "USER"

    assert "password" not in data
    assert "hashed_password" not in data

    user = database_session.execute(
        select(User).where(
            User.email == "auth-user@example.com"
        )
    ).scalar_one()

    assert user.hashed_password != PASSWORD

    assert verify_password(
        PASSWORD,
        user.hashed_password,
    ) is True


def test_register_duplicate_email_returns_409(
    client,
):
    payload = register_payload()

    first_response = client.post(
        "/auth/register",
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/auth/register",
        json=payload,
    )

    assert second_response.status_code == 409


def test_register_short_password_returns_422(
    client,
):
    payload = register_payload()
    payload["password"] = "short"

    response = client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 422


def test_registration_cannot_choose_admin_role(
    client,
):
    payload = register_payload()

    payload["role"] = "ADMIN"

    response = client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 422


def test_login_success(
    client,
):
    register_response = client.post(
        "/auth/register",
        json=register_payload(),
    )

    assert register_response.status_code == 201

    response = client.post(
        "/auth/login",
        json={
            "email": "auth-user@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["token_type"] == "bearer"
    assert data["access_token"]

    payload = decode_access_token(
        data["access_token"]
    )

    assert payload["role"] == "USER"

    assert payload["sub"] == str(
        register_response.json()["id"]
    )


def test_login_wrong_password_returns_401(
    client,
):
    client.post(
        "/auth/register",
        json=register_payload(),
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "auth-user@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401

    assert response.json()["detail"] == (
        "Invalid email or password"
    )


def test_login_unknown_email_returns_401(
    client,
):
    response = client.post(
        "/auth/login",
        json={
            "email": "does-not-exist@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 401

    assert response.json()["detail"] == (
        "Invalid email or password"
    )


def test_get_me_with_valid_token(
    client,
):
    register_response = client.post(
        "/auth/register",
        json=register_payload(),
    )

    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "email": "auth-user@example.com",
            "password": PASSWORD,
        },
    )

    token = login_response.json()[
        "access_token"
    ]

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["email"] == (
        "auth-user@example.com"
    )

    assert data["role"] == "USER"


def test_get_me_without_token_returns_401(
    client,
):
    response = client.get(
        "/auth/me"
    )

    assert response.status_code == 401

    assert response.json()["detail"] == (
        "Could not validate credentials"
    )


def test_get_me_with_invalid_token_returns_401(
    client,
):
    response = client.get(
        "/auth/me",
        headers={
            "Authorization": (
                "Bearer definitely-not-a-valid-jwt"
            )
        },
    )

    assert response.status_code == 401

    assert response.json()["detail"] == (
        "Could not validate credentials"
    )


def test_admin_token_returns_admin_user(
    client,
    admin_headers,
    admin_user,
):
    response = client.get(
        "/auth/me",
        headers=admin_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == admin_user.id
    assert data["role"] == "ADMIN"