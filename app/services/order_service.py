import hashlib
import json
from sqlalchemy.dialects.postgresql import insert

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_interaction import (
    InteractionType,
    ProductInteraction,
)
from app.models.user import User
from app.schemas.order import OrderCreate, OrderStatusUpdate
from app.cache.product_cache import invalidate_product_cache

class UserNotFoundError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class EmptyOrderError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class InvalidOrderStatusTransitionError(Exception):
    pass

class IdempotencyConflictError(Exception):
    pass

VALID_ORDER_STATUS_TRANSITIONS = {
    OrderStatus.PENDING: {
        OrderStatus.CONFIRMED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.CONFIRMED: {
        OrderStatus.SHIPPED,
    },
    OrderStatus.SHIPPED: {
        OrderStatus.DELIVERED,
    },
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}

def build_order_request_hash(
    order_data: OrderCreate,
) -> str:
    # Line order does not affect request identity.
    # Separate duplicate lines remain separate lines.
    normalized_items = sorted(
        (item.product_id, item.quantity)
        for item in order_data.items
    )

    canonical_json = json.dumps(
        {
            "version": 1,
            "items": normalized_items,
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


def find_idempotent_order(
    db: Session,
    user_id: int,
    idempotency_key: str,
    request_hash: str,
) -> Order | None:
    order = db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(
            Order.user_id == user_id,
            Order.idempotency_key == idempotency_key,
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()

    if (
        order is not None
        and order.idempotency_request_hash != request_hash
    ):
        raise IdempotencyConflictError(
            "Idempotency-Key was already used "
            "with different order contents"
        )

    return order
def create_order_in_transaction(
    db: Session,
    order_data: OrderCreate,
    *,
    idempotency_key: str | None = None,
) -> tuple[Order, list[int]]:
    """
    Create an order inside the caller's transaction.

    Does not commit, roll back, or invalidate caches.
    Returns the order and product IDs whose inventory changed.
    The caller must roll back if this function raises.
    """
    user_id = order_data.user_id

    request_hash = (
        build_order_request_hash(order_data)
        if idempotency_key is not None
        else None
    )

    # Return successful retries before checking current stock.
    if idempotency_key is not None:
        existing = find_idempotent_order(
            db,
            user_id,
            idempotency_key,
            request_hash,
        )

        if existing is not None:
            return existing, []

    if not order_data.items:
        raise EmptyOrderError(
            "Order must contain at least one item"
        )

    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError(
            f"User {user_id} not found"
        )

    statement = insert(Order).values(
        user_id=user_id,
        status=OrderStatus.PENDING,
        total_amount=Decimal("0.00"),
        idempotency_key=idempotency_key,
        idempotency_request_hash=request_hash,
    )

    if idempotency_key is not None:
        statement = statement.on_conflict_do_nothing(
            constraint="uq_orders_user_id_idempotency_key",
        )

    order = db.scalars(
        statement.returning(Order)
    ).one_or_none()

    if order is None:
        # Another request committed this key while we waited.
        existing = find_idempotent_order(
            db,
            user_id,
            idempotency_key,
            request_hash,
        )

        if existing is None:
            raise RuntimeError(
                "Idempotent order could not be loaded "
                "after an insert conflict"
            )

        return existing, []

    quantities_by_product: dict[int, int] = {}

    for item_data in order_data.items:
        product_id = item_data.product_id

        quantities_by_product[product_id] = (
            quantities_by_product.get(product_id, 0)
            + item_data.quantity
        )

    product_ids = sorted(quantities_by_product)

    products = db.execute(
        select(Product)
        .where(Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalars().all()

    products_by_id = {
        product.id: product
        for product in products
    }

    for product_id in product_ids:
        product = products_by_id.get(product_id)

        if product is None:
            raise ProductNotFoundError(
                f"Product {product_id} not found"
            )

        if (
            product.stock_quantity
            < quantities_by_product[product_id]
        ):
            raise InsufficientStockError(
                f"Insufficient stock for product {product.id}"
            )

    total_amount = Decimal("0.00")

    for item_data in order_data.items:
        product = products_by_id[item_data.product_id]
        unit_price = product.price

        total_amount += unit_price * item_data.quantity

        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item_data.quantity,
                unit_price=unit_price,
            )
        )

        product.stock_quantity -= item_data.quantity
        product.reserved_quantity += item_data.quantity

        db.add(
            ProductInteraction(
                user_id=user_id,
                product_id=product.id,
                interaction_type=InteractionType.ORDER_PLACED,
            )
        )

    order.total_amount = total_amount

    # Send pending writes to PostgreSQL without committing.
    db.flush()

    return order, product_ids


def create_order(
    db: Session,
    order_data: OrderCreate,
    *,
    idempotency_key: str | None = None,
) -> Order:
    try:
        order, changed_product_ids = (
            create_order_in_transaction(
                db,
                order_data,
                idempotency_key=idempotency_key,
            )
        )

        order_id = order.id
        db.commit()

    except Exception:
        db.rollback()
        raise

    # Invalidate only after the database commit succeeds.
    for product_id in changed_product_ids:
        invalidate_product_cache(product_id)

    return db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
        .execution_options(populate_existing=True)
    ).scalar_one()



def get_order(
    db: Session,
    order_id: int,
) -> Order | None:

    result = db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )

    return result.scalar_one_or_none()


def get_orders(
    db: Session,
) -> list[Order]:

    result = db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .order_by(Order.id)
    )

    return list(result.scalars().all())
def get_orders_for_user(
    db: Session,
    user_id: int,
) -> list[Order]:
    result = db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.user_id == user_id)
        .order_by(Order.id)
    )

    return list(
        result.scalars().unique().all()
    )

def update_order_status(
    db: Session,
    order_id: int,
    status_data: OrderStatusUpdate,
) -> Order:
    changed_product_ids: list[int] = []

    try:
        order = db.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()

        if order is None:
            raise OrderNotFoundError(
                f"Order {order_id} not found"
            )

        next_status = status_data.status
        allowed_statuses = VALID_ORDER_STATUS_TRANSITIONS[
            order.status
        ]

        if next_status not in allowed_statuses:
            raise InvalidOrderStatusTransitionError(
                f"Cannot change order {order_id} "
                f"from {order.status.value} "
                f"to {next_status.value}"
            )

        if next_status in {
            OrderStatus.CANCELLED,
            OrderStatus.SHIPPED,
        }:
            quantities_by_product: dict[int, int] = {}

            for item in order.items:
                quantities_by_product[item.product_id] = (
                    quantities_by_product.get(item.product_id, 0)
                    + item.quantity
                )

            changed_product_ids = sorted(quantities_by_product)

            products = db.execute(
                select(Product)
                .where(Product.id.in_(changed_product_ids))
                .order_by(Product.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).scalars().all()

            products_by_id = {
                product.id: product
                for product in products
            }

            # Validate every reservation before changing any counter.
            for product_id in changed_product_ids:
                product = products_by_id.get(product_id)
                quantity = quantities_by_product[product_id]

                if (
                    product is None
                    or product.reserved_quantity < quantity
                ):
                    raise RuntimeError(
                        "Inventory reservation inconsistency "
                        f"for order {order_id}, product {product_id}"
                    )

            for product_id in changed_product_ids:
                product = products_by_id[product_id]
                quantity = quantities_by_product[product_id]

                product.reserved_quantity -= quantity

                if next_status == OrderStatus.CANCELLED:
                    product.stock_quantity += quantity

        order.status = next_status
        db.commit()

    except Exception:
        db.rollback()
        raise

    for product_id in changed_product_ids:
        invalidate_product_cache(product_id)

    updated_order = get_order(db, order_id)

    if updated_order is None:
        raise OrderNotFoundError(
            f"Order {order_id} not found"
        )

    return updated_order