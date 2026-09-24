from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from queue import Queue
from time import monotonic, sleep

import pytest
from sqlalchemy import func, select, text

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_interaction import ProductInteraction
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.order_service import (
    InsufficientStockError,
    create_order,
    IdempotencyConflictError
)


def wait_until_both_buyers_are_blocked(
    session_factory,
    buyer_pids,
    futures,
):
    deadline = monotonic() + 5

    with session_factory() as monitor:
        while monotonic() < deadline:
            for future in futures:
                if future.done():
                    # Surface unexpected worker exceptions.
                    outcome = future.result()

                    pytest.fail(
                        "A buyer finished before the inventory "
                        f"lock was released: {outcome}"
                    )

            blocked = [
                bool(
                    monitor.scalar(
                        text("SELECT pg_blocking_pids(:pid)"),
                        {"pid": pid},
                    )
                )
                for pid in buyer_pids
            ]

            if all(blocked):
                return

            sleep(0.05)

    pytest.fail(
        "Both buyers did not reach a database lock wait "
        "within 5 seconds."
    )


@pytest.mark.parametrize(
    "starting_stock, expected_created, expected_rejected",
    [
        pytest.param(1, 1, 1, id="last-unit"),
        pytest.param(2, 2, 0, id="enough-for-both"),
    ],
)
def test_concurrent_orders_preserve_inventory(
    database_session,
    session_factory,
    make_user,
    starting_stock,
    expected_created,
    expected_rejected,
):
    first_user = make_user(email="buyer1@example.com")
    second_user = make_user(email="buyer2@example.com")
    user_ids = [first_user.id, second_user.id]

    product = Product(
        name="Concurrency Test Product",
        sku=f"CONCURRENT-{starting_stock}",
        price=Decimal("25.00"),
        stock_quantity=starting_stock,
    )

    database_session.add(product)
    database_session.commit()
    product_id = product.id

    buyer_pid_queue = Queue()

    def place_order(user_id):
        # Each worker owns its own Session.
        with session_factory() as db:
            db.execute(
                text("SET LOCAL lock_timeout = '15s'")
            )
            db.execute(
                text("SET LOCAL statement_timeout = '20s'")
            )

            assert db.scalar(
                text("SHOW transaction_isolation")
            ) == "read committed"

            # Keep a previously loaded Product in the Session.
            # The service must refresh it after obtaining its lock.
            loaded_product = db.get(Product, product_id)
            assert loaded_product is not None
            assert loaded_product.stock_quantity == starting_stock

            buyer_pid_queue.put(
                db.scalar(text("SELECT pg_backend_pid()"))
            )

            order_data = OrderCreate(
                user_id=user_id,
                items=[
                    OrderItemCreate(
                        product_id=product_id,
                        quantity=1,
                    )
                ],
            )

            try:
                order = create_order(db, order_data)
            except InsufficientStockError:
                return "insufficient_stock", None

            return "created", order.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        with session_factory() as holder:
            try:
                # Hold the product lock before either buyer starts.
                holder.execute(
                    select(Product)
                    .where(Product.id == product_id)
                    .with_for_update()
                ).scalar_one()

                futures = [
                    executor.submit(place_order, user_id)
                    for user_id in user_ids
                ]

                buyer_pids = [
                    buyer_pid_queue.get(timeout=5)
                    for _ in futures
                ]

                assert len(set(buyer_pids)) == 2

                wait_until_both_buyers_are_blocked(
                    session_factory,
                    buyer_pids,
                    futures,
                )

                # Let the buyers compete for the product lock.
                holder.commit()

            finally:
                # Release the holder's lock even if an assertion fails.
                holder.rollback()

        outcomes = [
            future.result(timeout=10)
            for future in futures
        ]

    statuses = [status for status, _ in outcomes]
    created_ids = [
        order_id
        for status, order_id in outcomes
        if status == "created"
    ]

    assert statuses.count("created") == expected_created
    assert statuses.count("insufficient_stock") == expected_rejected
    assert len(set(created_ids)) == expected_created

    # A fresh Session verifies committed database state.
    with session_factory() as verify:
        saved_product = verify.get(Product, product_id)
        assert saved_product is not None
        assert saved_product.stock_quantity == 0

        orders = list(
            verify.scalars(
                select(Order).where(Order.user_id.in_(user_ids))
            ).all()
        )

        assert {order.id for order in orders} == set(created_ids)
        assert all(
            order.total_amount == Decimal("25.00")
            for order in orders
        )

        item_count = verify.scalar(
            select(func.count())
            .select_from(OrderItem)
            .where(OrderItem.product_id == product_id)
        )
        assert item_count == expected_created

        interaction_count = verify.scalar(
            select(func.count())
            .select_from(ProductInteraction)
            .where(ProductInteraction.product_id == product_id)
        )
        assert interaction_count == expected_created
@pytest.mark.parametrize(
    "second_quantity",
    [
        pytest.param(1, id="same-key-same-contents"),
        pytest.param(2, id="same-key-different-contents"),
    ],
)
def test_concurrent_idempotency(
    database_session,
    session_factory,
    test_user,
    second_quantity,
):
    user_id = test_user.id
    product = Product(
        name="Idempotency Product",
        sku="IDEMPOTENCY-CONCURRENT",
        price=Decimal("25.00"),
        stock_quantity=2,
        is_active=True,
    )
    database_session.add(product)
    database_session.commit()
    product_id = product.id

    pid_queue = Queue()

    def place_order(quantity):
        with session_factory() as db:
            db.execute(text("SET LOCAL lock_timeout = '15s'"))
            db.execute(text("SET LOCAL statement_timeout = '20s'"))
            pid_queue.put(
                db.scalar(text("SELECT pg_backend_pid()"))
            )

            try:
                order = create_order(
                    db,
                    OrderCreate(
                        user_id=user_id,
                        items=[
                            OrderItemCreate(
                                product_id=product_id,
                                quantity=quantity,
                            )
                        ],
                    ),
                    idempotency_key="simultaneous-checkout",
                )
            except IdempotencyConflictError:
                return "conflict", None

            return "ok", order.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        with session_factory() as holder:
            try:
                holder.execute(
                    select(Product)
                    .where(Product.id == product_id)
                    .with_for_update()
                ).scalar_one()

                futures = [
                    executor.submit(place_order, quantity)
                    for quantity in (1, second_quantity)
                ]
                pids = [pid_queue.get(timeout=5) for _ in futures]

                assert len(set(pids)) == 2

                wait_until_both_buyers_are_blocked(
                    session_factory,
                    pids,
                    futures,
                )
                holder.commit()
            finally:
                holder.rollback()

        outcomes = [future.result(timeout=10) for future in futures]

    successful_ids = [
        order_id
        for outcome, order_id in outcomes
        if outcome == "ok"
    ]

    expected_successes = 2 if second_quantity == 1 else 1
    assert len(successful_ids) == expected_successes
    assert len(set(successful_ids)) == 1
    assert sum(
        outcome == "conflict" for outcome, _ in outcomes
    ) == 2 - expected_successes

    with session_factory() as verify:
        order = verify.execute(select(Order)).scalar_one()
        item = verify.execute(select(OrderItem)).scalar_one()

        assert order.id == successful_ids[0]
        assert item.order_id == order.id
        assert order.idempotency_key == "simultaneous-checkout"
        assert order.total_amount == Decimal("25.00") * item.quantity
        assert verify.get(
            Product, product_id
        ).stock_quantity == 2 - item.quantity

        assert verify.scalar(
            select(func.count()).select_from(ProductInteraction)
        ) == 1