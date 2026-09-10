from typing import Any
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cache.product_cache import (
    get_cached_product,
    invalidate_product_cache,
    set_cached_product,
)

from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate


class ProductAlreadyExistsError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


def create_product(
    database_session: Session,
    product_data: ProductCreate,
) -> Product:
    product = Product(
        name=product_data.name,
        description=product_data.description,
        sku=product_data.sku,
        price=product_data.price,
        stock_quantity=product_data.stock_quantity,
        is_active=product_data.is_active,
    )

    database_session.add(product)

    try:
        database_session.commit()
    except IntegrityError as error:
        database_session.rollback()
        raise ProductAlreadyExistsError(
            f"Product with SKU '{product_data.sku}' already exists"
        ) from error

    database_session.refresh(product)

    return product


def list_products(
    database_session: Session,
    skip: int = 0,
    limit: int = 20,
) -> list[Product]:
    statement = (
        select(Product)
        .order_by(Product.id)
        .offset(skip)
        .limit(limit)
    )

    return list(
        database_session.scalars(statement).all()
    )


def get_product(
    database_session: Session,
    product_id: int,
) -> Product:
    product = database_session.get(Product, product_id)

    if product is None:
        raise ProductNotFoundError(
            f"Product with ID {product_id} was not found"
        )

    return product
def get_product_for_read(
    database_session: Session,
    product_id: int,
) -> Product | dict[str, Any]:
    cached_product = get_cached_product(product_id)

    if cached_product is not None:
        return cached_product

    product = get_product(
        database_session=database_session,
        product_id=product_id,
    )

    set_cached_product(product)

    return product


def update_product(
    database_session: Session,
    product_id: int,
    product_data: ProductUpdate,
) -> Product:
    product = get_product(
        database_session=database_session,
        product_id=product_id,
    )

    update_values = product_data.model_dump(
        exclude_unset=True
    )

    for field_name, field_value in update_values.items():
        setattr(product, field_name, field_value)

    database_session.commit()
    database_session.refresh(product)
    invalidate_product_cache(product_id)

    return product


def delete_product(
    database_session: Session,
    product_id: int,
) -> None:
    product = get_product(
        database_session=database_session,
        product_id=product_id,
    )

    database_session.delete(product)
    database_session.commit()
    invalidate_product_cache(product_id)