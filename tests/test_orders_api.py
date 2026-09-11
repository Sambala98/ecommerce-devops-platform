from decimal import Decimal

from sqlalchemy import select

from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_interaction import (
    InteractionType,
    ProductInteraction,
)
from app.models.user import User


def create_test_user(database_session):
    user = User(
        email="order-user@example.com",
        name="Order User",
    )

    database_session.add(user)
    database_session.commit()
    database_session.refresh(user)

    return user


def create_test_product(
    database_session,
    *,
    stock_quantity=10,
    price=Decimal("19.99"),
):
    product = Product(
        name="Order Test Mouse",
        description="Product used for order tests",
        sku="ORDER-TEST-MOUSE-001",
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
):
    user = create_test_user(database_session)
    product = create_test_product(database_session)

    response = client.post(
        "/orders",
        json={
            "user_id": user.id,
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                }
            ],
        },
    )

    assert response.status_code == 201

    return response.json()


def test_create_order_success(client, database_session):
    user = create_test_user(database_session)
    product = create_test_product(database_session)

    response = client.post(
        "/orders",
        json={
            "user_id": user.id,
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 2,
                }
            ],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["user_id"] == user.id
    assert data["status"] == "PENDING"
    assert Decimal(str(data["total_amount"])) == Decimal("39.98")

    assert len(data["items"]) == 1

    item = data["items"][0]

    assert item["product_id"] == product.id
    assert item["quantity"] == 2
    assert Decimal(str(item["unit_price"])) == Decimal("19.99")

    database_session.expire_all()

    updated_product = database_session.get(
        Product,
        product.id,
    )

    assert updated_product.stock_quantity == 8


def test_order_creates_order_item(client, database_session):
    user = create_test_user(database_session)
    product = create_test_product(database_session)

    response = client.post(
        "/orders",
        json={
            "user_id": user.id,
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 2,
                }
            ],
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
    assert order_item.unit_price == Decimal("19.99")


def test_order_creates_purchase_interaction(
    client,
    database_session,
):
    user = create_test_user(database_session)
    product = create_test_product(database_session)

    response = client.post(
        "/orders",
        json={
            "user_id": user.id,
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                }
            ],
        },
    )

    assert response.status_code == 201

    interaction = database_session.execute(
        select(ProductInteraction).where(
            ProductInteraction.user_id == user.id,
            ProductInteraction.product_id == product.id,
        )
    ).scalar_one()

    assert (
        interaction.interaction_type
        == InteractionType.PURCHASE
    )


def test_missing_user_returns_404(
    client,
    database_session,
):
    product = create_test_product(database_session)

    response = client.post(
        "/orders",
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

    assert response.status_code == 404

    orders = database_session.execute(
        select(Order)
    ).scalars().all()

    assert orders == []


def test_missing_product_rolls_back_order(
    client,
    database_session,
):
    user = create_test_user(database_session)

    response = client.post(
        "/orders",
        json={
            "user_id": user.id,
            "items": [
                {
                    "product_id": 999999,
                    "quantity": 1,
                }
            ],
        },
    )

    assert response.status_code == 404

    database_session.expire_all()

    orders = database_session.execute(
        select(Order)
    ).scalars().all()

    interactions = database_session.execute(
        select(ProductInteraction)
    ).scalars().all()

    assert orders == []
    assert interactions == []


def test_insufficient_stock_rolls_back_everything(
    client,
    database_session,
):
    user = create_test_user(database_session)

    product = create_test_product(
        database_session,
        stock_quantity=1,
    )

    response = client.post(
        "/orders",
        json={
            "user_id": user.id,
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 2,
                }
            ],
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
    database_session,
):
    user = create_test_user(database_session)

    response = client.post(
        "/orders",
        json={
            "user_id": user.id,
            "items": [],
        },
    )

    assert response.status_code == 400


def test_get_order(client, database_session):
    user = create_test_user(database_session)
    product = create_test_product(database_session)

    create_response = client.post(
        "/orders",
        json={
            "user_id": user.id,
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                }
            ],
        },
    )

    assert create_response.status_code == 201

    order_id = create_response.json()["id"]

    response = client.get(
        f"/orders/{order_id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == order_id
    assert data["user_id"] == user.id
    assert len(data["items"]) == 1

def test_order_status_full_lifecycle(
    client,
    database_session,
):
    order = create_test_order(
        client,
        database_session,
    )

    order_id = order["id"]

    assert order["status"] == "PENDING"

    response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "CONFIRMED"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"

    response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "SHIPPED"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SHIPPED"

    response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "DELIVERED"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "DELIVERED"

    database_session.expire_all()

    persisted_order = database_session.get(
        Order,
        order_id,
    )

    assert persisted_order is not None
    assert persisted_order.status == OrderStatus.DELIVERED


def test_pending_order_can_be_cancelled(
    client,
    database_session,
):
    order = create_test_order(
        client,
        database_session,
    )

    response = client.patch(
        f"/orders/{order['id']}/status",
        json={"status": "CANCELLED"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_pending_to_delivered_returns_409(
    client,
    database_session,
):
    order = create_test_order(
        client,
        database_session,
    )

    response = client.patch(
        f"/orders/{order['id']}/status",
        json={"status": "DELIVERED"},
    )

    assert response.status_code == 409

    assert response.json()["detail"] == (
        f"Cannot change order {order['id']} "
        "from PENDING to DELIVERED"
    )


def test_delivered_order_is_terminal(
    client,
    database_session,
):
    order = create_test_order(
        client,
        database_session,
    )

    order_id = order["id"]

    client.patch(
        f"/orders/{order_id}/status",
        json={"status": "CONFIRMED"},
    )

    client.patch(
        f"/orders/{order_id}/status",
        json={"status": "SHIPPED"},
    )

    client.patch(
        f"/orders/{order_id}/status",
        json={"status": "DELIVERED"},
    )

    response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "PENDING"},
    )

    assert response.status_code == 409

    assert response.json()["detail"] == (
        f"Cannot change order {order_id} "
        "from DELIVERED to PENDING"
    )


def test_cancelled_order_is_terminal(
    client,
    database_session,
):
    order = create_test_order(
        client,
        database_session,
    )

    order_id = order["id"]

    cancel_response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "CANCELLED"},
    )

    assert cancel_response.status_code == 200

    response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "CONFIRMED"},
    )

    assert response.status_code == 409

    assert response.json()["detail"] == (
        f"Cannot change order {order_id} "
        "from CANCELLED to CONFIRMED"
    )


def test_update_status_missing_order_returns_404(
    client,
):
    response = client.patch(
        "/orders/999999/status",
        json={"status": "CONFIRMED"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Order 999999 not found"
    )


def test_invalid_order_status_returns_422(
    client,
    database_session,
):
    order = create_test_order(
        client,
        database_session,
    )

    response = client.patch(
        f"/orders/{order['id']}/status",
        json={"status": "READY_FOR_PICKUP"},
    )

    assert response.status_code == 422