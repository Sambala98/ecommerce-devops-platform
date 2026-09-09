from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_interaction import (
    InteractionType,
    ProductInteraction,
)
from app.models.user import User
from app.schemas.order import OrderCreate


class UserNotFoundError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class EmptyOrderError(Exception):
    pass


def create_order(
    db: Session,
    order_data: OrderCreate,
) -> Order:

    if not order_data.items:
        raise EmptyOrderError(
            "Order must contain at least one item"
        )

    user = db.get(User, order_data.user_id)

    if user is None:
        raise UserNotFoundError(
            f"User {order_data.user_id} not found"
        )

    order = Order(
        user_id=user.id,
        total_amount=Decimal("0.00"),
    )

    db.add(order)
    db.flush()

    total_amount = Decimal("0.00")

    for item_data in order_data.items:

        product = db.get(
            Product,
            item_data.product_id,
        )

        if product is None:
            db.rollback()

            raise ProductNotFoundError(
                f"Product {item_data.product_id} not found"
            )

        if product.stock_quantity < item_data.quantity:
            db.rollback()

            raise InsufficientStockError(
                f"Insufficient stock for product {product.id}"
            )

        unit_price = product.price

        line_total = (
            unit_price * item_data.quantity
        )

        total_amount += line_total

        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=item_data.quantity,
            unit_price=unit_price,
        )

        db.add(order_item)

        product.stock_quantity -= item_data.quantity

        interaction = ProductInteraction(
            user_id=user.id,
            product_id=product.id,
            interaction_type=InteractionType.PURCHASE,
        )

        db.add(interaction)

    order.total_amount = total_amount

    try:
        db.commit()

    except Exception:
        db.rollback()
        raise

    result = db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order.id)
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