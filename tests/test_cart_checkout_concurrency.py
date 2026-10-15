from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from queue import Queue
from time import monotonic, sleep

import pytest
from sqlalchemy import select, text

from app.models.cart_item import CartItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_interaction import (
    InteractionType,
    ProductInteraction,
)
from app.services.cart_service import (
    EmptyCartError,
    checkout_cart,
    lock_user_cart,
)
from threading import Event

from app.schemas.cart import CartItemSetRequest
from app.services.cart_service import (
    remove_cart_item,
    set_cart_item,
)


def wait_for_blocked_checkouts(
    session_factory,
    worker_pids,
    futures,
):
    deadline = monotonic() + 5

    with session_factory() as monitor:
        while monotonic() < deadline:
            for future in futures:
                if future.done():
                    outcome = future.result()
                    pytest.fail(
                        "Checkout finished while the cart lock "
                        f"was still held: {outcome}"
                    )

            blocked = [
                bool(
                    monitor.scalar(
                        text("SELECT pg_blocking_pids(:pid)"),
                        {"pid": pid},
                    )
                )
                for pid in worker_pids
            ]

            if all(blocked):
                return

            sleep(0.05)

    pytest.fail(
        "Both checkout workers did not reach a database "
        "lock wait within 5 seconds."
    )


@pytest.mark.parametrize(
    "same_key",
    [
        pytest.param(True, id="same-key"),
        pytest.param(False, id="different-keys"),
    ],
)
def test_overlapping_checkouts_create_one_order(
    database_session,
    session_factory,
    test_user,
    same_key,
):
    user_id = test_user.id

    product = Product(
        name="Concurrent Checkout Product",
        sku="CHECKOUT-CONCURRENT-001",
        price=Decimal("25.00"),
        stock_quantity=5,
        reserved_quantity=0,
        is_active=True,
    )
    database_session.add(product)
    database_session.flush()
    product_id = product.id

    database_session.add(
        CartItem(
            user_id=user_id,
            product_id=product_id,
            quantity=2,
        )
    )
    database_session.commit()

    keys = (
        ("checkout-a", "checkout-a")
        if same_key
        else ("checkout-a", "checkout-b")
    )

    pid_queue = Queue()

    def run_checkout(key):
        # Never share a SQLAlchemy session between workers.
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

            pid_queue.put(
                db.scalar(text("SELECT pg_backend_pid()"))
            )

            try:
                result = checkout_cart(
                    db=db,
                    user_id=user_id,
                    idempotency_key=key,
                )
            except EmptyCartError:
                return "empty", None, key

            return "ok", result.id, key

    with ThreadPoolExecutor(max_workers=2) as executor:
        with session_factory() as holder:
            try:
                # Hold the cart lock until both requests
                # have reached an actual database lock wait.
                lock_user_cart(holder, user_id)

                futures = [
                    executor.submit(run_checkout, key)
                    for key in keys
                ]

                worker_pids = [
                    pid_queue.get(timeout=5)
                    for _ in futures
                ]
                assert len(set(worker_pids)) == 2

                wait_for_blocked_checkouts(
                    session_factory,
                    worker_pids,
                    futures,
                )
            finally:
                # Release before waiting for worker results.
                holder.rollback()

        outcomes = [
            future.result(timeout=25)
            for future in futures
        ]

    successes = [
        outcome for outcome in outcomes
        if outcome[0] == "ok"
    ]
    empty_results = [
        outcome for outcome in outcomes
        if outcome[0] == "empty"
    ]

    if same_key:
        assert len(successes) == 2
        assert len(empty_results) == 0
        assert successes[0][1] == successes[1][1]
    else:
        assert len(successes) == 1
        assert len(empty_results) == 1

    order_id = successes[0][1]
    winning_key = successes[0][2]

    with session_factory() as db:
        orders = db.scalars(select(Order)).all()
        assert len(orders) == 1

        order = orders[0]
        assert order.id == order_id
        assert order.user_id == user_id
        assert order.checkout_idempotency_key == winning_key
        assert order.total_amount == Decimal("50.00")
        assert order.idempotency_key is None

        items = db.scalars(select(OrderItem)).all()
        assert len(items) == 1
        assert items[0].order_id == order_id
        assert items[0].product_id == product_id
        assert items[0].quantity == 2

        events = db.scalars(select(ProductInteraction)).all()
        assert len(events) == 1
        assert events[0].user_id == user_id
        assert events[0].product_id == product_id
        assert events[0].interaction_type == InteractionType.ORDER_PLACED

        assert db.scalar(select(CartItem.id)) is None

        saved_product = db.get(Product, product_id)
        assert saved_product.stock_quantity == 3
        assert saved_product.reserved_quantity == 2
        assert saved_product.on_hand_quantity == 5

@pytest.mark.parametrize("mutation", ["set", "remove"])
@pytest.mark.parametrize("checkout_first", [True, False])
def test_checkout_and_cart_mutation_are_serialized(
    database_session,
    session_factory,
    test_user,
    mutation,
    checkout_first,
):
    user_id = test_user.id

    product = Product(
        name="Checkout Mutation Product",
        sku="CHECKOUT-MUTATION-001",
        price=Decimal("25.00"),
        stock_quantity=5,
        reserved_quantity=0,
        is_active=True,
    )
    database_session.add(product)
    database_session.flush()
    product_id = product.id

    database_session.add(
        CartItem(
            user_id=user_id,
            product_id=product_id,
            quantity=2,
        )
    )
    database_session.commit()

    first_has_lock = Event()
    release_first = Event()
    second_pid_queue = Queue()

    def perform_operation(db, operation):
        if operation == "checkout":
            try:
                order = checkout_cart(
                    db=db,
                    user_id=user_id,
                    idempotency_key="checkout-mutation-001",
                )
            except EmptyCartError:
                return "empty", None

            return "order", order.id

        if mutation == "set":
            set_cart_item(
                db=db,
                user_id=user_id,
                product_id=product_id,
                item_data=CartItemSetRequest(quantity=1),
            )
        else:
            remove_cart_item(
                db=db,
                user_id=user_id,
                product_id=product_id,
            )

        return "mutated", None

    def run_worker(operation, first):
        with session_factory() as db:
            db.execute(text("SET LOCAL lock_timeout = '15s'"))
            db.execute(text("SET LOCAL statement_timeout = '20s'"))

            assert db.scalar(
                text("SHOW transaction_isolation")
            ) == "read committed"

            if first:
                # Control which operation owns the cart first.
                # The service reuses this same transaction.
                lock_user_cart(db, user_id)
                first_has_lock.set()

                if not release_first.wait(timeout=10):
                    raise RuntimeError(
                        "Timed out waiting to release first operation"
                    )
            else:
                second_pid_queue.put(
                    db.scalar(text("SELECT pg_backend_pid()"))
                )

            return perform_operation(db, operation)

    first_operation = "checkout" if checkout_first else "mutation"
    second_operation = "mutation" if checkout_first else "checkout"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            run_worker, first_operation, True
        )

        try:
            assert first_has_lock.wait(timeout=5), (
                "First operation did not acquire the cart lock"
            )

            second_future = executor.submit(
                run_worker, second_operation, False
            )
            second_pid = second_pid_queue.get(timeout=5)

            # Reuse the existing helper with one waiting worker.
            # This proves the second operation honors the lock.
            wait_for_blocked_checkouts(
                session_factory,
                [second_pid],
                [second_future],
            )
        finally:
            release_first.set()

        first_result = first_future.result(timeout=25)
        second_result = second_future.result(timeout=25)

    checkout_result = (
        first_result if checkout_first else second_result
    )
    mutation_result = (
        second_result if checkout_first else first_result
    )
    assert mutation_result == ("mutated", None)

    if checkout_first:
        purchased_quantity = 2
        remaining_cart_quantity = 1 if mutation == "set" else None
    elif mutation == "set":
        purchased_quantity = 1
        remaining_cart_quantity = None
    else:
        purchased_quantity = 0
        remaining_cart_quantity = None

    with session_factory() as db:
        orders = db.scalars(select(Order)).all()
        items = db.scalars(select(OrderItem)).all()
        events = db.scalars(select(ProductInteraction)).all()

        if purchased_quantity:
            assert checkout_result[0] == "order"
            assert len(orders) == 1
            assert orders[0].id == checkout_result[1]
            assert orders[0].user_id == user_id
            assert orders[0].total_amount == (
                Decimal("25.00") * purchased_quantity
            )

            assert len(items) == 1
            assert items[0].order_id == orders[0].id
            assert items[0].product_id == product_id
            assert items[0].quantity == purchased_quantity

            assert len(events) == 1
            assert events[0].interaction_type == (
                InteractionType.ORDER_PLACED
            )
        else:
            assert checkout_result == ("empty", None)
            assert orders == []
            assert items == []
            assert events == []

        cart = db.scalars(select(CartItem)).all()

        if remaining_cart_quantity is None:
            assert cart == []
        else:
            assert len(cart) == 1
            assert cart[0].user_id == user_id
            assert cart[0].product_id == product_id
            assert cart[0].quantity == remaining_cart_quantity

        saved_product = db.get(Product, product_id)
        assert saved_product.stock_quantity == 5 - purchased_quantity
        assert saved_product.reserved_quantity == purchased_quantity
        assert saved_product.on_hand_quantity == 5