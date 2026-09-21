from decimal import Decimal

from sqlalchemy import select

from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_interaction import (
    InteractionType,
    ProductInteraction,
)


def create_test_product(
    database_session,
    *,
    stock_quantity: int = 10,
    price: Decimal = Decimal("19.99"),
    sku: str = "ORDER-TEST-MOUSE-001",
):
    product = Product(
        name="Order Test Mouse",
        description="Product used for order tests",
        sku=sku,
        price=price,
        stock_quantity=stock_quantity,
        is_active=True,
    )

    database_session.add(product)
    database_session.commit()
    database_session.refresh(product)

    return product


def create_test_order(
    client,
    database_session,
    user_headers,
    *,
    quantity: int = 1,
):
    product = create_test_product(
        database_session,
    )

    response = client.post(
        "/orders",
        headers=user_headers,
        json={
            "items": [
                {
                    "product_id": product.id,
                    "quantity": quantity,
                }
            ]
        },
    )

    assert response.status_code == 201

    return response.json(), product


def test_create_order_requires_authentication(
    client,
    database_session,
):
    product = create_test_product(
        database_session,
    )

    response = client.post(
        "/orders",
        json={
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                }
            ]
        },
    )

    assert response.status_code == 401


def test_client_cannot_choose_order_user(
    client,
    database_session,
    user_headers,
):
    product = create_test_product(
        database_session,
    )

    response = client.post(
        "/orders",
        headers=user_headers,
        json={
            "user_id": 999999,
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                }
            ],
        },
    )

    assert response.status_code == 422

    errors = response.json()["detail"]

    assert any(
        error["loc"] == ["body", "user_id"]
        and error["type"] == "extra_forbidden"
        for error in errors
    )


def test_create_order_uses_authenticated_user(
    client,
    database_session,
    test_user,
    user_headers,
):
    product = create_test_product(
        database_session,
    )

    response = client.post(
        "/orders",
        headers=user_headers,
        json={
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 2,
                }
            ]
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["user_id"] == test_user.id
    assert data["status"] == "PENDING"

    assert (
        Decimal(str(data["total_amount"]))
        == Decimal("39.98")
    )

    assert len(data["items"]) == 1

    item = data["items"][0]

    assert item["product_id"] == product.id
    assert item["quantity"] == 2

    assert (
        Decimal(str(item["unit_price"]))
        == Decimal("19.99")
    )

    database_session.expire_all()

    updated_product = database_session.get(
        Product,
        product.id,
    )

    assert updated_product.stock_quantity == 8


def test_order_creates_order_item(
    client,
    database_session,
    user_headers,
):
    product = create_test_product(
        database_session,
    )

    response = client.post(
        "/orders",
        headers=user_headers,
        json={
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 2,
                }
            ]
        },
    )

    assert response.status_code == 201

    order_id = response.json()["id"]

    order_item = database_session.execute(
        select(OrderItem).where(
            OrderItem.order_id == order_id
        )
    ).scalar_one()

    assert order_item.product_id == product.id
    assert order_item.quantity == 2

    assert (
        order_item.unit_price
        == Decimal("19.99")
    )


def test_order_creates_purchase_interaction(
    client,
    database_session,
    test_user,
    user_headers,
):
    product = create_test_product(
        database_session,
    )

    response = client.post(
        "/orders",
        headers=user_headers,
        json={
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                }
            ]
        },
    )

    assert response.status_code == 201

    interaction = database_session.execute(
        select(ProductInteraction).where(
            ProductInteraction.user_id
            == test_user.id,
            ProductInteraction.product_id
            == product.id,
        )
    ).scalar_one()

    assert (
        interaction.interaction_type
        == InteractionType.PURCHASE
    )


def test_missing_product_rolls_back_order(
    client,
    database_session,
    user_headers,
):
    response = client.post(
        "/orders",
        headers=user_headers,
        json={
            "items": [
                {
                    "product_id": 999999,
                    "quantity": 1,
                }
            ]
        },
    )

    assert response.status_code == 404

    database_session.expire_all()

    orders = database_session.execute(
        select(Order)
    ).scalars().all()

    order_items = database_session.execute(
        select(OrderItem)
    ).scalars().all()

    interactions = database_session.execute(
        select(ProductInteraction)
    ).scalars().all()

    assert orders == []
    assert order_items == []
    assert interactions == []


def test_insufficient_stock_rolls_back_everything(
    client,
    database_session,
    user_headers,
):
    product = create_test_product(
        database_session,
        stock_quantity=1,
    )

    response = client.post(
        "/orders",
        headers=user_headers,
        json={
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 2,
                }
            ]
        },
    )

    assert response.status_code == 409

    database_session.expire_all()

    updated_product = database_session.get(
        Product,
        product.id,
    )

    assert updated_product.stock_quantity == 1

    orders = database_session.execute(
        select(Order)
    ).scalars().all()

    order_items = database_session.execute(
        select(OrderItem)
    ).scalars().all()

    interactions = database_session.execute(
        select(ProductInteraction)
    ).scalars().all()

    assert orders == []
    assert order_items == []
    assert interactions == []


def test_empty_order_returns_400(
    client,
    user_headers,
):
    response = client.post(
        "/orders",
        headers=user_headers,
        json={
            "items": [],
        },
    )

    assert response.status_code == 400


def test_owner_can_get_own_order(
    client,
    database_session,
    test_user,
    user_headers,
):
    order, _ = create_test_order(
        client,
        database_session,
        user_headers,
    )

    response = client.get(
        f"/orders/{order['id']}",
        headers=user_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == order["id"]
    assert data["user_id"] == test_user.id


def test_other_user_cannot_get_order(
    client,
    database_session,
    user_headers,
    make_user,
    auth_headers_for,
):
    order, _ = create_test_order(
        client,
        database_session,
        user_headers,
    )

    other_user = make_user(
        email="other@example.com",
    )

    other_headers = auth_headers_for(
        other_user
    )

    response = client.get(
        f"/orders/{order['id']}",
        headers=other_headers,
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You do not have access to this order"
    )


def test_admin_can_get_any_order(
    client,
    database_session,
    user_headers,
    admin_headers,
):
    order, _ = create_test_order(
        client,
        database_session,
        user_headers,
    )

    response = client.get(
        f"/orders/{order['id']}",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == order["id"]


def test_user_order_list_contains_only_own_orders(
    client,
    database_session,
    test_user,
    user_headers,
    make_user,
    auth_headers_for,
):
    first_product = create_test_product(
        database_session,
        sku="ORDER-USER-001",
    )

    first_response = client.post(
        "/orders",
        headers=user_headers,
        json={
            "items": [
                {
                    "product_id": first_product.id,
                    "quantity": 1,
                }
            ]
        },
    )

    assert first_response.status_code == 201

    other_user = make_user(
        email="another-user@example.com",
    )

    other_headers = auth_headers_for(
        other_user
    )

    second_product = create_test_product(
        database_session,
        sku="ORDER-USER-002",
    )

    second_response = client.post(
        "/orders",
        headers=other_headers,
        json={
            "items": [
                {
                    "product_id": second_product.id,
                    "quantity": 1,
                }
            ]
        },
    )

    assert second_response.status_code == 201

    response = client.get(
        "/orders",
        headers=user_headers,
    )

    assert response.status_code == 200

    orders = response.json()

    assert len(orders) == 1

    assert all(
        order["user_id"] == test_user.id
        for order in orders
    )


def test_admin_order_list_contains_all_orders(
    client,
    database_session,
    user_headers,
    admin_headers,
    make_user,
    auth_headers_for,
):
    product_one = create_test_product(
        database_session,
        sku="ADMIN-LIST-001",
    )

    response_one = client.post(
        "/orders",
        headers=user_headers,
        json={
            "items": [
                {
                    "product_id": product_one.id,
                    "quantity": 1,
                }
            ]
        },
    )

    assert response_one.status_code == 201

    other_user = make_user(
        email="order-list-user@example.com",
    )

    other_headers = auth_headers_for(
        other_user
    )

    product_two = create_test_product(
        database_session,
        sku="ADMIN-LIST-002",
    )

    response_two = client.post(
        "/orders",
        headers=other_headers,
        json={
            "items": [
                {
                    "product_id": product_two.id,
                    "quantity": 1,
                }
            ]
        },
    )

    assert response_two.status_code == 201

    response = client.get(
        "/orders",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_normal_user_cannot_update_order_status(
    client,
    database_session,
    user_headers,
):
    order, _ = create_test_order(
        client,
        database_session,
        user_headers,
    )

    response = client.patch(
        f"/orders/{order['id']}/status",
        headers=user_headers,
        json={
            "status": "CONFIRMED",
        },
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "Admin access required"
    )


def test_order_status_full_lifecycle(
    client,
    database_session,
    user_headers,
    admin_headers,
):
    order, _ = create_test_order(
        client,
        database_session,
        user_headers,
    )

    order_id = order["id"]

    assert order["status"] == "PENDING"

    response = client.patch(
        f"/orders/{order_id}/status",
        headers=admin_headers,
        json={
            "status": "CONFIRMED",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"

    response = client.patch(
        f"/orders/{order_id}/status",
        headers=admin_headers,
        json={
            "status": "SHIPPED",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SHIPPED"

    response = client.patch(
        f"/orders/{order_id}/status",
        headers=admin_headers,
        json={
            "status": "DELIVERED",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "DELIVERED"

    database_session.expire_all()

    persisted_order = database_session.get(
        Order,
        order_id,
    )

    assert persisted_order is not None

    assert (
        persisted_order.status
        == OrderStatus.DELIVERED
    )



def test_pending_order_can_be_cancelled(
    client,
    database_session,
    user_headers,
    admin_headers,
):
    order, product = create_test_order(
        client,
        database_session,
        user_headers,
        quantity=2,
    )

    database_session.expire_all()

    product_after_order = (
        database_session.get(
            Product,
            product.id,
        )
    )

    assert (
        product_after_order.stock_quantity
        == 8
    )

    response = client.patch(
        f"/orders/{order['id']}/status",
        headers=admin_headers,
        json={
            "status": "CANCELLED",
        },
    )

    assert response.status_code == 200

    assert (
        response.json()["status"]
        == "CANCELLED"
    )

    database_session.expire_all()

    restored_product = (
        database_session.get(
            Product,
            product.id,
        )
    )

    assert (
        restored_product.stock_quantity
        == 10
    )

def test_cancelled_order_does_not_restore_stock_twice(
    client,
    database_session,
    user_headers,
    admin_headers,
):
    order, product = create_test_order(
        client,
        database_session,
        user_headers,
        quantity=2,
    )

    first_response = client.patch(
        f"/orders/{order['id']}/status",
        headers=admin_headers,
        json={
            "status": "CANCELLED",
        },
    )

    assert first_response.status_code == 200

    database_session.expire_all()

    restored_product = (
        database_session.get(
            Product,
            product.id,
        )
    )

    assert (
        restored_product.stock_quantity
        == 10
    )

    second_response = client.patch(
        f"/orders/{order['id']}/status",
        headers=admin_headers,
        json={
            "status": "CANCELLED",
        },
    )

    assert second_response.status_code == 409

    database_session.expire_all()

    product_after_second_attempt = (
        database_session.get(
            Product,
            product.id,
        )
    )

    assert (
        product_after_second_attempt.stock_quantity
        == 10
    )
def test_pending_to_delivered_returns_409(
    client,
    database_session,
    user_headers,
    admin_headers,
):
    order, _ = create_test_order(
        client,
        database_session,
        user_headers,
    )

    response = client.patch(
        f"/orders/{order['id']}/status",
        headers=admin_headers,
        json={
            "status": "DELIVERED",
        },
    )

    assert response.status_code == 409

    assert response.json()["detail"] == (
        f"Cannot change order {order['id']} "
        "from PENDING to DELIVERED"
    )


def test_delivered_order_is_terminal(
    client,
    database_session,
    user_headers,
    admin_headers,
):
    order, _ = create_test_order(
        client,
        database_session,
        user_headers,
    )

    order_id = order["id"]

    for next_status in (
        "CONFIRMED",
        "SHIPPED",
        "DELIVERED",
    ):
        response = client.patch(
            f"/orders/{order_id}/status",
            headers=admin_headers,
            json={
                "status": next_status,
            },
        )

        assert response.status_code == 200

    response = client.patch(
        f"/orders/{order_id}/status",
        headers=admin_headers,
        json={
            "status": "PENDING",
        },
    )

    assert response.status_code == 409

    assert response.json()["detail"] == (
        f"Cannot change order {order_id} "
        "from DELIVERED to PENDING"
    )


def test_cancelled_order_is_terminal(
    client,
    database_session,
    user_headers,
    admin_headers,
):
    order, _ = create_test_order(
        client,
        database_session,
        user_headers,
    )

    order_id = order["id"]

    cancel_response = client.patch(
        f"/orders/{order_id}/status",
        headers=admin_headers,
        json={
            "status": "CANCELLED",
        },
    )

    assert cancel_response.status_code == 200

    response = client.patch(
        f"/orders/{order_id}/status",
        headers=admin_headers,
        json={
            "status": "CONFIRMED",
        },
    )

    assert response.status_code == 409

    assert response.json()["detail"] == (
        f"Cannot change order {order_id} "
        "from CANCELLED to CONFIRMED"
    )


def test_update_status_missing_order_returns_404(
    client,
    admin_headers,
):
    response = client.patch(
        "/orders/999999/status",
        headers=admin_headers,
        json={
            "status": "CONFIRMED",
        },
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Order 999999 not found"
    )


def test_invalid_order_status_returns_422(
    client,
    database_session,
    user_headers,
    admin_headers,
):
    order, _ = create_test_order(
        client,
        database_session,
        user_headers,
    )

    response = client.patch(
        f"/orders/{order['id']}/status",
        headers=admin_headers,
        json={
            "status": "READY_FOR_PICKUP",
        },
    )

    assert response.status_code == 422