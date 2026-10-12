from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_interaction import ProductInteraction
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.order_service import (
    create_order_in_transaction,
)


@pytest.mark.parametrize(
    "commit_order",
    [
        pytest.param(False, id="caller-rolls-back"),
        pytest.param(True, id="caller-commits"),
    ],
)
def test_caller_controls_order_transaction(
    database_session,
    session_factory,
    test_user,
    commit_order,
):
    user_id = test_user.id

    product = Product(
        name="Transaction Test Product",
        sku="ORDER-TRANSACTION-001",
        price=Decimal("25.00"),
        stock_quantity=5,
        reserved_quantity=0,
        is_active=True,
    )

    database_session.add(product)
    database_session.commit()

    product_id = product.id

    with session_factory() as db:
        order, changed_product_ids = (
            create_order_in_transaction(
                db,
                OrderCreate(
                    user_id=user_id,
                    items=[
                        OrderItemCreate(
                            product_id=product_id,
                            quantity=2,
                        )
                    ],
                ),
                idempotency_key="transaction-test",
            )
        )

        order_id = order.id

        assert changed_product_ids == [product_id]
        assert order.total_amount == Decimal("50.00")

        # Another connection must not see the order yet.
        with session_factory() as observer:
            assert observer.scalar(
                select(func.count())
                .select_from(Order)
                .where(Order.id == order_id)
            ) == 0

            unchanged_product = observer.get(
                Product,
                product_id,
            )

            assert unchanged_product.stock_quantity == 5
            assert unchanged_product.reserved_quantity == 0

        if commit_order:
            db.commit()
        else:
            # Simulate the caller abandoning the operation
            # after order creation has completed.
            db.rollback()

    expected_count = 1 if commit_order else 0

    with session_factory() as verify:
        assert verify.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.id == order_id)
        ) == expected_count

        assert verify.scalar(
            select(func.count())
            .select_from(OrderItem)
            .where(OrderItem.order_id == order_id)
        ) == expected_count

        assert verify.scalar(
            select(func.count())
            .select_from(ProductInteraction)
            .where(
                ProductInteraction.user_id == user_id,
                ProductInteraction.product_id == product_id,
            )
        ) == expected_count

        saved_product = verify.get(Product, product_id)

        assert saved_product is not None
        assert saved_product.stock_quantity == (
            3 if commit_order else 5
        )
        assert saved_product.reserved_quantity == (
            2 if commit_order else 0
        )