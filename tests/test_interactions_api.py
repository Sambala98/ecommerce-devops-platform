from sqlalchemy import select

from app.models.product_interaction import (
    InteractionType,
    ProductInteraction,
)


def create_user(client):
    response = client.post(
        "/users",
        json={
            "email": "interaction-user@example.com",
            "name": "Interaction Test User",
        },
    )

    assert response.status_code == 201

    return response.json()


def create_product(client):
    response = client.post(
        "/products",
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


def test_create_view_interaction(
    client,
):
    user = create_user(client)
    product = create_product(client)

    response = client.post(
        "/interactions",
        json={
            "user_id": user["id"],
            "product_id": product["id"],
            "interaction_type": "VIEW",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["user_id"] == user["id"]
    assert data["product_id"] == product["id"]
    assert data["interaction_type"] == "VIEW"
    assert data["id"] is not None
    assert data["created_at"] is not None


def test_create_add_to_cart_interaction(
    client,
):
    user = create_user(client)
    product = create_product(client)

    response = client.post(
        "/interactions",
        json={
            "user_id": user["id"],
            "product_id": product["id"],
            "interaction_type": "ADD_TO_CART",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["interaction_type"] == "ADD_TO_CART"


def test_purchase_interaction_is_rejected(
    client,
):
    user = create_user(client)
    product = create_product(client)

    response = client.post(
        "/interactions",
        json={
            "user_id": user["id"],
            "product_id": product["id"],
            "interaction_type": "PURCHASE",
        },
    )

    assert response.status_code == 422


def test_interaction_missing_user_returns_404(
    client,
):
    product = create_product(client)

    response = client.post(
        "/interactions",
        json={
            "user_id": 99999,
            "product_id": product["id"],
            "interaction_type": "VIEW",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "User with ID 99999 was not found"
    )


def test_interaction_missing_product_returns_404(
    client,
):
    user = create_user(client)

    response = client.post(
        "/interactions",
        json={
            "user_id": user["id"],
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
):
    user = create_user(client)
    product = create_product(client)

    response = client.post(
        "/interactions",
        json={
            "user_id": user["id"],
            "product_id": product["id"],
            "interaction_type": "VIEW",
        },
    )

    assert response.status_code == 201

    interaction_id = response.json()["id"]

    statement = select(ProductInteraction).where(
        ProductInteraction.id == interaction_id
    )

    interaction = database_session.scalar(statement)

    assert interaction is not None
    assert interaction.user_id == user["id"]
    assert interaction.product_id == product["id"]
    assert interaction.interaction_type == InteractionType.VIEW