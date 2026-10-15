from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.cart_item import CartItem
from app.models.product import Product


@pytest.fixture
def cart_product(database_session):
    product = Product(
        name="Cart Test Product",
        description="Product for cart tests",
        sku="CART-TEST-001",
        price=Decimal("19.99"),
        stock_quantity=5,
        reserved_quantity=0,
        is_active=True,
    )

    database_session.add(product)
    database_session.commit()
    database_session.refresh(product)

    return product


def test_cart_starts_empty(client, user_headers):
    response = client.get(
        "/cart",
        headers=user_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_set_retry_and_replace_quantity(
    client,
    database_session,
    user_headers,
    test_user,
    cart_product,
):
    url = f"/cart/items/{cart_product.id}"

    first = client.put(
        url,
        headers=user_headers,
        json={"quantity": 2},
    )
    retry = client.put(
        url,
        headers=user_headers,
        json={"quantity": 2},
    )
    updated = client.put(
        url,
        headers=user_headers,
        json={"quantity": 5},
    )

    for response in (first, retry, updated):
        assert response.status_code == 200, response.text

    assert first.json()["quantity"] == 2
    assert retry.json()["quantity"] == 2
    assert updated.json()["quantity"] == 5
    assert first.json()["id"] == retry.json()["id"]
    assert first.json()["id"] == updated.json()["id"]

    rows = database_session.scalars(
        select(CartItem)
        .where(CartItem.user_id == test_user.id)
        .execution_options(populate_existing=True)
    ).all()

    assert len(rows) == 1
    assert rows[0].quantity == 5

    response = client.get("/cart", headers=user_headers)

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert response.json()[0]["quantity"] == 5

    database_session.refresh(cart_product)

    assert cart_product.stock_quantity == 5
    assert cart_product.reserved_quantity == 0


def test_cart_is_scoped_to_current_user(
    client,
    user_headers,
    admin_headers,
    cart_product,
):
    url = f"/cart/items/{cart_product.id}"

    response = client.put(
        url,
        headers=user_headers,
        json={"quantity": 2},
    )
    assert response.status_code == 200, response.text

    response = client.get("/cart", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json() == []

    response = client.put(
        url,
        headers=admin_headers,
        json={"quantity": 4},
    )
    assert response.status_code == 200, response.text

    response = client.delete(url, headers=admin_headers)
    assert response.status_code == 204
    assert response.content == b""

    response = client.get("/cart", headers=user_headers)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert response.json()[0]["quantity"] == 2


def test_remove_can_be_retried(
    client,
    user_headers,
    cart_product,
):
    url = f"/cart/items/{cart_product.id}"

    response = client.put(
        url,
        headers=user_headers,
        json={"quantity": 2},
    )
    assert response.status_code == 200, response.text

    for _ in range(2):
        response = client.delete(url, headers=user_headers)
        assert response.status_code == 204
        assert response.content == b""

    response = client.get("/cart", headers=user_headers)
    assert response.status_code == 200, response.text
    assert response.json() == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"quantity": 0},
        {"quantity": -1},
        {"quantity": 1_000_001},
        {"quantity": 1.5},
        {"quantity": True},
        {"quantity": "2"},
        {"quantity": None},
        {"quantity": 2, "user_id": 999},
        {"quantity": 2, "price": "0.01"},
    ],
)
def test_invalid_cart_payload_is_rejected(
    client,
    database_session,
    user_headers,
    cart_product,
    payload,
):
    response = client.put(
        f"/cart/items/{cart_product.id}",
        headers=user_headers,
        json=payload,
    )

    assert response.status_code == 422, response.text
    assert database_session.scalar(select(CartItem)) is None


def test_missing_cart_product_returns_404(
    client,
    database_session,
    user_headers,
    cart_product,
):
    missing_id = cart_product.id
    database_session.delete(cart_product)
    database_session.commit()

    response = client.put(
        f"/cart/items/{missing_id}",
        headers=user_headers,
        json={"quantity": 1},
    )

    assert response.status_code == 404, response.text
    assert database_session.scalar(select(CartItem)) is None


def test_inactive_cart_product_returns_409(
    client,
    database_session,
    user_headers,
    cart_product,
):
    cart_product.is_active = False
    database_session.commit()

    response = client.put(
        f"/cart/items/{cart_product.id}",
        headers=user_headers,
        json={"quantity": 1},
    )

    assert response.status_code == 409, response.text
    assert database_session.scalar(select(CartItem)) is None


def test_sold_out_product_can_be_saved_without_reservation(
    client,
    database_session,
    user_headers,
    cart_product,
):
    cart_product.stock_quantity = 0
    database_session.commit()

    response = client.put(
        f"/cart/items/{cart_product.id}",
        headers=user_headers,
        json={"quantity": 2},
    )

    assert response.status_code == 200, response.text
    assert response.json()["quantity"] == 2

    database_session.refresh(cart_product)

    assert cart_product.stock_quantity == 0
    assert cart_product.reserved_quantity == 0


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_cart_requires_authentication(
    client,
    database_session,
    cart_product,
    method,
):
    if method == "GET":
        response = client.get("/cart")
    elif method == "PUT":
        response = client.put(
            f"/cart/items/{cart_product.id}",
            json={"quantity": 1},
        )
    else:
        response = client.delete(
            f"/cart/items/{cart_product.id}",
        )

    assert response.status_code == 401, response.text
    assert database_session.scalar(select(CartItem)) is None