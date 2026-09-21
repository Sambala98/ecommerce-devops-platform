from sqlalchemy import select

from app.models.product_interaction import (
    InteractionType,
    ProductInteraction,
)


def create_product(
    client,
    admin_headers,
):
    response = client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "Interaction Test Product",
            "description": "Used for interaction tests",
            "sku": "INTERACTION-TEST-001",
            "price": 39.99,
            "stock_quantity": 25,
            "is_active": True,
        },
    )

    assert response.status_code == 201

    return response.json()


def test_interaction_requires_authentication(
    client,
    admin_headers,
):
    product = create_product(
        client,
        admin_headers,
    )

    response = client.post(
        "/interactions",
        json={
            "product_id": product["id"],
            "interaction_type": "VIEW",
        },
    )

    assert response.status_code == 401

    assert response.json()["detail"] == (
        "Could not validate credentials"
    )


def test_create_view_interaction(
    client,
    admin_headers,
    user_headers,
    test_user,
):
    product = create_product(
        client,
        admin_headers,
    )

    response = client.post(
        "/interactions",
        headers=user_headers,
        json={
            "product_id": product["id"],
            "interaction_type": "VIEW",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["user_id"] == test_user.id
    assert data["product_id"] == product["id"]
    assert data["interaction_type"] == "VIEW"
    assert data["id"] is not None
    assert data["created_at"] is not None


def test_create_add_to_cart_interaction(
    client,
    admin_headers,
    user_headers,
    test_user,
):
    product = create_product(
        client,
        admin_headers,
    )

    response = client.post(
        "/interactions",
        headers=user_headers,
        json={
            "product_id": product["id"],
            "interaction_type": "ADD_TO_CART",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["user_id"] == test_user.id
    assert data["product_id"] == product["id"]

    assert (
        data["interaction_type"]
        == "ADD_TO_CART"
    )


def test_client_cannot_choose_interaction_user(
    client,
    admin_headers,
    user_headers,
):
    product = create_product(
        client,
        admin_headers,
    )

    response = client.post(
        "/interactions",
        headers=user_headers,
        json={
            "user_id": 99999,
            "product_id": product["id"],
            "interaction_type": "VIEW",
        },
    )

    assert response.status_code == 422

    errors = response.json()["detail"]

    assert any(
        error["loc"] == ["body", "user_id"]
        and error["type"] == "extra_forbidden"
        for error in errors
    )


def test_purchase_interaction_is_rejected(
    client,
    admin_headers,
    user_headers,
):
    product = create_product(
        client,
        admin_headers,
    )

    response = client.post(
        "/interactions",
        headers=user_headers,
        json={
            "product_id": product["id"],
            "interaction_type": "PURCHASE",
        },
    )

    assert response.status_code == 422


def test_interaction_missing_product_returns_404(
    client,
    user_headers,
):
    response = client.post(
        "/interactions",
        headers=user_headers,
        json={
            "product_id": 99999,
            "interaction_type": "ADD_TO_CART",
        },
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Product with ID 99999 was not found"
    )


def test_interaction_is_persisted(
    client,
    database_session,
    admin_headers,
    user_headers,
    test_user,
):
    product = create_product(
        client,
        admin_headers,
    )

    response = client.post(
        "/interactions",
        headers=user_headers,
        json={
            "product_id": product["id"],
            "interaction_type": "VIEW",
        },
    )

    assert response.status_code == 201

    interaction_id = response.json()["id"]

    statement = select(
        ProductInteraction
    ).where(
        ProductInteraction.id
        == interaction_id
    )

    interaction = database_session.scalar(
        statement
    )

    assert interaction is not None

    assert (
        interaction.user_id
        == test_user.id
    )

    assert (
        interaction.product_id
        == product["id"]
    )

    assert (
        interaction.interaction_type
        == InteractionType.VIEW
    )