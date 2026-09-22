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

def create_order(
    db: Session,
    order_data: OrderCreate,
) -> Order:
    try:
        if not order_data.items:
            raise EmptyOrderError(
                "Order must contain at least one item"
            )

        user = db.get(User, order_data.user_id)

        if user is None:
            raise UserNotFoundError(
                f"User {order_data.user_id} not found"
            )

        # Combine requested quantities for stock validation.
        # Preserve the original order lines below.
        quantities_by_product: dict[int, int] = {}

        for item_data in order_data.items:
            product_id = item_data.product_id

            quantities_by_product[product_id] = (
                quantities_by_product.get(product_id, 0)
                + item_data.quantity
            )

        product_ids = sorted(quantities_by_product)

        # Lock products before checking or changing inventory.
        # Refresh objects already loaded in this Session.
        product_result = db.execute(
            select(Product)
            .where(Product.id.in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        products_by_id = {
            product.id: product
            for product in product_result.scalars().all()
        }

        # Validate every product before creating the order.
        for product_id in product_ids:
            product = products_by_id.get(product_id)

            if product is None:
                raise ProductNotFoundError(
                    f"Product {product_id} not found"
                )

            requested_quantity = quantities_by_product[
                product_id
            ]

            if product.stock_quantity < requested_quantity:
                raise InsufficientStockError(
                    f"Insufficient stock for product {product.id}"
                )

        order = Order(
            user_id=user.id,
            total_amount=Decimal("0.00"),
        )

        db.add(order)
        db.flush()

        total_amount = Decimal("0.00")

        for item_data in order_data.items:
            product = products_by_id[item_data.product_id]
            unit_price = product.price

            total_amount += (
                unit_price * item_data.quantity
            )

            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=item_data.quantity,
                    unit_price=unit_price,
                )
            )

            product.stock_quantity -= item_data.quantity

            db.add(
                ProductInteraction(
                    user_id=user.id,
                    product_id=product.id,
                    interaction_type=InteractionType.PURCHASE,
                )
            )

        order.total_amount = total_amount
        order_id = order.id

        db.commit()

    except Exception:
        db.rollback()
        raise

    # This read happens after the write transaction committed.
    result = db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )

    return result.scalar_one()


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

    result = db.execute(
        select(Order)
        .options(
            selectinload(Order.items)
        )
        .where(
            Order.id == order_id
        )
        .with_for_update()
    )

    order = result.scalar_one_or_none()

    if order is None:
        db.rollback()

        raise OrderNotFoundError(
            f"Order {order_id} not found"
        )

    allowed_statuses = (
        VALID_ORDER_STATUS_TRANSITIONS[
            order.status
        ]
    )

    if (
        status_data.status
        not in allowed_statuses
    ):
        db.rollback()

        raise InvalidOrderStatusTransitionError(
            f"Cannot change order {order_id} "
            f"from {order.status.value} "
            f"to {status_data.status.value}"
        )

    if (
        status_data.status
        == OrderStatus.CANCELLED
    ):
        product_ids = sorted(
            {
                item.product_id
                for item in order.items
            }
        )

        if product_ids:
            product_result = db.execute(
                select(Product)
                .where(
                    Product.id.in_(
                        product_ids
                    )
                )
                .order_by(Product.id)
                .with_for_update()
            )

            products = list(
                product_result.scalars().all()
            )

            products_by_id = {
                product.id: product
                for product in products
            }

            for item in order.items:
                product = products_by_id[
                    item.product_id
                ]

                product.stock_quantity += (
                    item.quantity
                )

    order.status = status_data.status

    try:
        db.commit()

    except Exception:
        db.rollback()
        raise

    updated_order = get_order(
        db,
        order_id,
    )

    if updated_order is None:
        raise OrderNotFoundError(
            f"Order {order_id} not found"
        )

    return updated_order