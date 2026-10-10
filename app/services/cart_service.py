from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.cart_item import CartItem
from app.models.product import Product
from app.schemas.cart import (
    CartItemResponse,
    CartItemSetRequest,
)


class CartProductNotFoundError(Exception):
    pass


class CartProductInactiveError(Exception):
    pass


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