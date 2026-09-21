def new_user_payload():
    return {
        "email": "created-by-admin@example.com",
        "name": "Created User",
        "password": "StrongPassword123!",
    }


def test_list_users_requires_authentication(
    client,
):
    response = client.get(
        "/users"
    )

    assert response.status_code == 401


def test_normal_user_cannot_list_users(
    client,
    user_headers,
):
    response = client.get(
        "/users",
        headers=user_headers,
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "Admin access required"
    )


def test_admin_can_list_users(
    client,
    test_user,
    admin_user,
    admin_headers,
):
    response = client.get(
        "/users",
        headers=admin_headers,
    )

    assert response.status_code == 200

    users = response.json()

    returned_ids = {
        user["id"]
        for user in users
    }

    assert test_user.id in returned_ids
    assert admin_user.id in returned_ids


def test_normal_user_cannot_create_user(
    client,
    user_headers,
):
    response = client.post(
        "/users",
        headers=user_headers,
        json=new_user_payload(),
    )

    assert response.status_code == 403


def test_admin_can_create_user(
    client,
    admin_headers,
):
    response = client.post(
        "/users",
        headers=admin_headers,
        json=new_user_payload(),
    )

    assert response.status_code == 201

    data = response.json()

    assert (
        data["email"]
        == "created-by-admin@example.com"
    )

    assert data["role"] == "USER"

    assert "password" not in data
    assert "hashed_password" not in data


def test_user_can_get_self(
    client,
    test_user,
    user_headers,
):
    response = client.get(
        f"/users/{test_user.id}",
        headers=user_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == test_user.id
    assert data["email"] == test_user.email


def test_user_cannot_get_another_user(
    client,
    test_user,
    user_headers,
    make_user,
):
    other_user = make_user(
        email="other-user@example.com",
    )

    response = client.get(
        f"/users/{other_user.id}",
        headers=user_headers,
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You do not have access to this user"
    )


def test_admin_can_get_any_user(
    client,
    test_user,
    admin_headers,
):
    response = client.get(
        f"/users/{test_user.id}",
        headers=admin_headers,
    )

    assert response.status_code == 200

    assert (
        response.json()["id"]
        == test_user.id
    )


def test_admin_get_missing_user_returns_404(
    client,
    admin_headers,
):
    response = client.get(
        "/users/999999",
        headers=admin_headers,
    )

    assert response.status_code == 404