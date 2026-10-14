from sqlalchemy import delete, func, select,text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.cart_item import CartItem
from app.models.product import Product
from app.schemas.cart import (
    CartItemResponse,
    CartItemSetRequest,
)
from app.models.order import Order
from app.schemas.order import (
    OrderCreate,
    OrderItemCreate,
    OrderResponse,
)
from app.services.order_service import (
    create_order_in_transaction,
    get_order,
)
from app.cache.product_cache import invalidate_product_cache

class CartProductNotFoundError(Exception):
    pass


class CartProductInactiveError(Exception):
    pass

class EmptyCartError(Exception):
    pass

# Application-reserved advisory-lock namespace for carts.
CART_LOCK_NAMESPACE = 73101


def lock_user_cart(
    db: Session,
    user_id: int,
) -> None:
    """Hold this user's cart lock until commit or rollback.

    Cart mutations and checkout must acquire this lock
    before taking product or cart-item locks.
    """
    db.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            ":namespace, :user_id)"
        ),
        {
            "namespace": CART_LOCK_NAMESPACE,
            "user_id": user_id,
        },
    )


def get_cart(
    db: Session,
    user_id: int,
) -> list[CartItem]:
    statement = (
        select(CartItem)
        .where(CartItem.user_id == user_id)
        .order_by(CartItem.product_id)
        .execution_options(populate_existing=True)
    )

    return list(db.scalars(statement).all())


def set_cart_item(
    db: Session,
    user_id: int,
    product_id: int,
    item_data: CartItemSetRequest,
) -> CartItemResponse:
    try:
        # Keep the product from being deleted or changed
        # while we validate and write the cart item.
        lock_user_cart(db, user_id)
        product = db.scalar(
            select(Product)
            .where(Product.id == product_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )

        if product is None:
            raise CartProductNotFoundError(
                f"Product {product_id} not found"
            )

        if not product.is_active:
            raise CartProductInactiveError(
                f"Product {product_id} is inactive"
            )

        statement = insert(CartItem).values(
            user_id=user_id,
            product_id=product_id,
            quantity=item_data.quantity,
        )

        statement = statement.on_conflict_do_update(
            constraint="uq_cart_items_user_product",
            set_={
                "quantity": statement.excluded.quantity,
                "updated_at": func.now(),
            },
        ).returning(CartItem)

        item = db.scalars(
            statement,
            execution_options={
                "populate_existing": True,
            },
        ).one()

        # Capture the response before commit expires ORM state.
        response = CartItemResponse.model_validate(item)

        db.commit()

        return response

    except Exception:
        db.rollback()
        raise


def remove_cart_item(
    db: Session,
    user_id: int,
    product_id: int,
) -> None:
    try:
        lock_user_cart(db, user_id)
        db.execute(
            delete(CartItem).where(
                CartItem.user_id == user_id,
                CartItem.product_id == product_id,
            )
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

def checkout_cart(
    db: Session,
    user_id: int,
    *,
    idempotency_key: str,
) -> OrderResponse:
    changed_product_ids: list[int] = []

    try:
        # Same lock used by cart PUT and DELETE.
        lock_user_cart(db, user_id)

        # Check retries before reading the current cart.
        existing_order_id = db.scalar(
            select(Order.id).where(
                Order.user_id == user_id,
                Order.checkout_idempotency_key == idempotency_key,
            )
        )

        if existing_order_id is not None:
            order = get_order(db, existing_order_id)

            if order is None:
                raise RuntimeError(
                    "Previous checkout order could not be loaded"
                )

            response = OrderResponse.model_validate(order)
            db.commit()
            return response

        cart_items = get_cart(db, user_id)

        if not cart_items:
            raise EmptyCartError("Cart is empty")

        # Copy values before making any database changes.
        order_items = [
            OrderItemCreate(
                product_id=item.product_id,
                quantity=item.quantity,
            )
            for item in cart_items
        ]

        product_ids = sorted(
            item.product_id for item in order_items
        )

        # Lock products in the same order as order creation.
        # Hold these locks through validation and commit.
        products = db.scalars(
            select(Product)
            .where(Product.id.in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()

        products_by_id = {
            product.id: product
            for product in products
        }

        for product_id in product_ids:
            product = products_by_id.get(product_id)

            if product is None:
                raise CartProductNotFoundError(
                    f"Product {product_id} not found"
                )

            if not product.is_active:
                raise CartProductInactiveError(
                    f"Product {product_id} is inactive"
                )

        # Reuse inventory, pricing, and interaction logic.
        # Direct-order idempotency fields stay NULL.
        order, changed_product_ids = (
            create_order_in_transaction(
                db,
                OrderCreate(
                    user_id=user_id,
                    items=order_items,
                ),
            )
        )

        order.checkout_idempotency_key = idempotency_key

        db.execute(
            delete(CartItem).where(
                CartItem.user_id == user_id,
            )
        )

        db.flush()

        # Load items and validate the response before commit.
        saved_order = get_order(db, order.id)

        if saved_order is None:
            raise RuntimeError(
                "Checkout order could not be loaded"
            )

        response = OrderResponse.model_validate(saved_order)

        # Order, inventory, events, key, and cart clearing
        # become permanent together.
        db.commit()

    except Exception:
        db.rollback()
        raise

    # Database commit must succeed before invalidation.
    for product_id in changed_product_ids:
        invalidate_product_cache(product_id)

    return response