from decimal import Decimal

import pytest
from sqlalchemy import select

import app.services.cart_service as cart_service
from app.models.cart_item import CartItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_interaction import (
    InteractionType,
    ProductInteraction,
)


@pytest.fixture
def checkout_product(database_session):
    product = Product(
        name="Checkout Test Product",
        sku="CHECKOUT-TEST-001",
        price=Decimal("25.00"),
        stock_quantity=5,
        reserved_quantity=0,
        is_active=True,
    )
    database_session.add(product)
    database_session.commit()
    return product


def add_to_cart(client, headers, product_id, quantity=2):
    response = client.put(
        f"/cart/items/{product_id}",
        headers=headers,
        json={"quantity": quantity},
    )
    assert response.status_code == 200, response.text


def checkout(client, headers, key="checkout-001"):
    return client.post(
        "/cart/checkout",
        headers={
            **headers,
            "Idempotency-Key": key,
        },
    )


def assert_no_order_writes(db):
    for model in (Order, OrderItem, ProductInteraction):
        assert db.scalar(select(model.id).limit(1)) is None


def test_checkout_commits_order_inventory_and_cart(
    client,
    user_headers,
    test_user,
    checkout_product,
    session_factory,
):
    product_id = checkout_product.id
    user_id = test_user.id
    add_to_cart(client, user_headers, product_id)

    response = checkout(client, user_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == user_id
    assert body["status"] == "PENDING"
    assert Decimal(body["total_amount"]) == Decimal("50.00")
    assert len(body["items"]) == 1
    assert body["items"][0]["product_id"] == product_id
    assert body["items"][0]["quantity"] == 2
    assert Decimal(body["items"][0]["unit_price"]) == Decimal("25.00")

    # A fresh session verifies committed database state.
    with session_factory() as db:
        orders = db.scalars(select(Order)).all()
        assert len(orders) == 1
        assert orders[0].id == body["id"]
        assert orders[0].checkout_idempotency_key == "checkout-001"
        assert orders[0].idempotency_key is None
        assert orders[0].idempotency_request_hash is None

        assert db.scalar(select(CartItem.id)) is None

        product = db.get(Product, product_id)
        assert product.stock_quantity == 3
        assert product.reserved_quantity == 2
        assert product.on_hand_quantity == 5

        items = db.scalars(select(OrderItem)).all()
        assert len(items) == 1
        assert items[0].order_id == body["id"]
        assert items[0].quantity == 2

        events = db.scalars(select(ProductInteraction)).all()
        assert len(events) == 1
        assert events[0].user_id == user_id
        assert events[0].product_id == product_id
        assert events[0].interaction_type == InteractionType.ORDER_PLACED


def test_retry_preserves_items_added_after_checkout(
    client,
    user_headers,
    checkout_product,
    session_factory,
):
    product_id = checkout_product.id
    add_to_cart(client, user_headers, product_id)

    first = checkout(client, user_headers)
    assert first.status_code == 200, first.text

    # Retry while the cart is empty.
    retry = checkout(client, user_headers)
    assert retry.status_code == 200, retry.text
    assert retry.json() == first.json()

    # Add items for a future purchase, then replay the old key.
    add_to_cart(client, user_headers, product_id, quantity=1)

    replay = checkout(client, user_headers)
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()

    with session_factory() as db:
        assert len(db.scalars(select(Order)).all()) == 1
        assert len(db.scalars(select(OrderItem)).all()) == 1
        assert len(db.scalars(select(ProductInteraction)).all()) == 1

        cart = db.scalars(select(CartItem)).all()
        assert len(cart) == 1
        assert cart[0].quantity == 1

        product = db.get(Product, product_id)
        assert product.stock_quantity == 3
        assert product.reserved_quantity == 2


@pytest.mark.parametrize("reason", ["insufficient-stock", "inactive"])
def test_checkout_failure_preserves_cart_and_inventory(
    client,
    database_session,
    user_headers,
    checkout_product,
    session_factory,
    reason,
):
    product_id = checkout_product.id
    add_to_cart(client, user_headers, product_id)

    if reason == "insufficient-stock":
        checkout_product.stock_quantity = 1
        expected_stock = 1
    else:
        checkout_product.is_active = False
        expected_stock = 5

    database_session.commit()

    response = checkout(client, user_headers)

    assert response.status_code == 409, response.text

    with session_factory() as db:
        assert_no_order_writes(db)

        cart = db.scalars(select(CartItem)).all()
        assert len(cart) == 1
        assert cart[0].quantity == 2

        product = db.get(Product, product_id)
        assert product.stock_quantity == expected_stock
        assert product.reserved_quantity == 0

def test_failure_after_cart_delete_rolls_back_everything(
    client,
    user_headers,
    checkout_product,
    session_factory,
    monkeypatch,
):
    product_id = checkout_product.id
    add_to_cart(client, user_headers, product_id)

    invalidations = []
    monkeypatch.setattr(
        cart_service,
        "invalidate_product_cache",
        invalidations.append,
    )

    failure_reached = []

    def fail_before_commit(db, order_id):
        # Verify the writes happened inside the transaction.
        assert db.get(Order, order_id) is not None
        assert db.scalar(select(CartItem.id)) is None

        product = db.get(Product, product_id)
        assert product.stock_quantity == 3
        assert product.reserved_quantity == 2

        failure_reached.append(True)
        raise RuntimeError("Injected checkout failure")

    monkeypatch.setattr(
        cart_service,
        "get_order",
        fail_before_commit,
    )

    response = checkout(client, user_headers)

    assert failure_reached == [True]
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers.get("X-Request-ID")

    # A fresh session verifies that all writes were rolled back.
    with session_factory() as db:
        assert_no_order_writes(db)

        cart = db.scalars(select(CartItem)).all()
        assert len(cart) == 1
        assert cart[0].quantity == 2

        product = db.get(Product, product_id)
        assert product.stock_quantity == 5
        assert product.reserved_quantity == 0

    # A rolled-back checkout must not invalidate caches.
    assert invalidations == []



def test_empty_cart_returns_400(
    client,
    user_headers,
    session_factory,
):
    response = checkout(client, user_headers)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Cart is empty"

    with session_factory() as db:
        assert_no_order_writes(db)


def test_checkout_requires_authentication(client):
    response = checkout(client, {})
    assert response.status_code == 401, response.text


@pytest.mark.parametrize(
    "key",
    [None, "", "contains spaces", "x" * 129],
)
def test_invalid_checkout_key_does_not_change_cart(
    client,
    user_headers,
    checkout_product,
    session_factory,
    key,
):
    product_id = checkout_product.id
    add_to_cart(client, user_headers, product_id)

    headers = dict(user_headers)
    if key is not None:
        headers["Idempotency-Key"] = key

    response = client.post(
        "/cart/checkout",
        headers=headers,
    )

    assert response.status_code == 422, response.text

    with session_factory() as db:
        assert_no_order_writes(db)

        cart = db.scalars(select(CartItem)).all()
        assert len(cart) == 1
        assert cart[0].quantity == 2

        product = db.get(Product, product_id)
        assert product.stock_quantity == 5
        assert product.reserved_quantity == 0
def test_checkout_key_is_scoped_to_user(
    client,
    user_headers,
    test_user,
    make_user,
    auth_headers_for,
    checkout_product,
    session_factory,
):
    product_id = checkout_product.id
    first_user_id = test_user.id

    other_user = make_user("checkout-other@example.com")
    other_user_id = other_user.id
    other_headers = auth_headers_for(other_user)

    add_to_cart(client, user_headers, product_id, quantity=2)
    add_to_cart(client, other_headers, product_id, quantity=1)

    first = checkout(client, user_headers, key="shared-key")
    second = checkout(client, other_headers, key="shared-key")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["user_id"] == first_user_id
    assert second.json()["user_id"] == other_user_id
    assert Decimal(first.json()["total_amount"]) == Decimal("50.00")
    assert Decimal(second.json()["total_amount"]) == Decimal("25.00")

    for headers, original in (
        (user_headers, first),
        (other_headers, second),
    ):
        replay = checkout(client, headers, key="shared-key")
        assert replay.status_code == 200, replay.text
        assert replay.json() == original.json()

    with session_factory() as db:
        orders = db.scalars(select(Order)).all()
        assert len(orders) == 2
        assert {order.user_id for order in orders} == {
            first_user_id,
            other_user_id,
        }
        assert all(
            order.checkout_idempotency_key == "shared-key"
            for order in orders
        )
        assert db.scalar(select(CartItem.id)) is None
        assert len(db.scalars(select(OrderItem)).all()) == 2
        assert len(db.scalars(select(ProductInteraction)).all()) == 2

        product = db.get(Product, product_id)
        assert product.stock_quantity == 2
        assert product.reserved_quantity == 3


@pytest.mark.parametrize("checkout_first", [False, True])
def test_checkout_and_direct_order_keys_are_separate(
    client,
    user_headers,
    checkout_product,
    session_factory,
    checkout_first,
):
    product_id = checkout_product.id
    key = "same-key-both-endpoints"

    add_to_cart(client, user_headers, product_id, quantity=2)

    def direct_order():
        return client.post(
            "/orders",
            headers={
                **user_headers,
                "Idempotency-Key": key,
            },
            json={
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 1,
                    }
                ]
            },
        )

    if checkout_first:
        cart_response = checkout(client, user_headers, key=key)
        direct_response = direct_order()
    else:
        direct_response = direct_order()
        cart_response = checkout(client, user_headers, key=key)

    assert cart_response.status_code == 200, cart_response.text
    assert direct_response.status_code == 201, direct_response.text

    cart_id = cart_response.json()["id"]
    direct_id = direct_response.json()["id"]
    assert cart_id != direct_id

    assert Decimal(
        cart_response.json()["total_amount"]
    ) == Decimal("50.00")
    assert Decimal(
        direct_response.json()["total_amount"]
    ) == Decimal("25.00")

    cart_retry = checkout(client, user_headers, key=key)
    direct_retry = direct_order()

    assert cart_retry.status_code == 200, cart_retry.text
    assert direct_retry.status_code == 201, direct_retry.text
    assert cart_retry.json() == cart_response.json()
    assert direct_retry.json() == direct_response.json()

    with session_factory() as db:
        assert len(db.scalars(select(Order)).all()) == 2
        assert len(db.scalars(select(OrderItem)).all()) == 2
        assert len(db.scalars(select(ProductInteraction)).all()) == 2
        assert db.scalar(select(CartItem.id)) is None

        cart_order = db.get(Order, cart_id)
        assert cart_order.checkout_idempotency_key == key
        assert cart_order.idempotency_key is None

        direct = db.get(Order, direct_id)
        assert direct.idempotency_key == key
        assert direct.checkout_idempotency_key is None

        product = db.get(Product, product_id)
        assert product.stock_quantity == 2
        assert product.reserved_quantity == 3