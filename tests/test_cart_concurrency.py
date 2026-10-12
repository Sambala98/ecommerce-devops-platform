from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from queue import Queue
from time import monotonic, sleep

import pytest
from sqlalchemy import select, text

from app.models.cart_item import CartItem
from app.models.product import Product
from app.schemas.cart import CartItemSetRequest
from app.services.cart_service import set_cart_item


def wait_until_cart_writers_are_blocked(
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
                        "A cart writer finished before the "
                        f"blocking transaction ended: {outcome}"
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
        "Both cart writers did not reach a database "
        "lock wait within 5 seconds."
    )


@pytest.mark.parametrize(
    "keep_seed_row",
    [
        pytest.param(False, id="new-item"),
        pytest.param(True, id="existing-item"),
    ],
)
@pytest.mark.parametrize(
    "second_quantity",
    [
        pytest.param(2, id="same-quantity"),
        pytest.param(5, id="different-quantities"),
    ],
)
def test_concurrent_cart_writes_preserve_one_row(
    database_session,
    session_factory,
    test_user,
    keep_seed_row,
    second_quantity,
):
    user_id = test_user.id

    product = Product(
        name="Concurrent Cart Product",
        sku="CART-CONCURRENT-001",
        price=Decimal("25.00"),
        stock_quantity=10,
        reserved_quantity=0,
        is_active=True,
    )

    database_session.add(product)
    database_session.commit()

    product_id = product.id
    pid_queue = Queue()

    def write_cart(quantity):
        # Each thread owns its own database session.
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

            result = set_cart_item(
                db=db,
                user_id=user_id,
                product_id=product_id,
                item_data=CartItemSetRequest(
                    quantity=quantity,
                ),
            )

            return result.id, result.quantity

    with ThreadPoolExecutor(max_workers=2) as executor:
        with session_factory() as holder:
            try:
                # An uncommitted row makes both upserts wait
                # on the same unique user/product key.
                seed = CartItem(
                    user_id=user_id,
                    product_id=product_id,
                    quantity=1,
                )

                holder.add(seed)
                holder.flush()
                seed_id = seed.id

                futures = [
                    executor.submit(write_cart, quantity)
                    for quantity in (2, second_quantity)
                ]

                worker_pids = [
                    pid_queue.get(timeout=5)
                    for _ in futures
                ]

                assert len(set(worker_pids)) == 2

                wait_until_cart_writers_are_blocked(
                    session_factory,
                    worker_pids,
                    futures,
                )

                if keep_seed_row:
                    # Workers must update this existing row.
                    holder.commit()
                else:
                    # Remove the uncommitted seed so workers
                    # compete to create the missing cart item.
                    holder.rollback()

            finally:
                # Release locks even if the test fails.
                holder.rollback()

        outcomes = [
            future.result(timeout=25)
            for future in futures
        ]

    returned_ids = [item_id for item_id, _ in outcomes]
    returned_quantities = [
        quantity for _, quantity in outcomes
    ]

    # Both callers succeed and refer to the same cart row.
    assert len(set(returned_ids)) == 1

    # Each response reflects that caller's requested quantity.
    assert returned_quantities == [2, second_quantity]

    if keep_seed_row:
        assert returned_ids[0] == seed_id

    # Read committed results using a fresh session.
    with session_factory() as verify:
        rows = list(
            verify.scalars(
                select(CartItem).where(
                    CartItem.user_id == user_id,
                    CartItem.product_id == product_id,
                )
            ).all()
        )

        assert len(rows) == 1
        assert rows[0].id == returned_ids[0]
        assert rows[0].quantity in {2, second_quantity}

        saved_product = verify.get(Product, product_id)

        assert saved_product is not None
        assert saved_product.stock_quantity == 10
        assert saved_product.reserved_quantity == 0
        assert saved_product.on_hand_quantity == 10