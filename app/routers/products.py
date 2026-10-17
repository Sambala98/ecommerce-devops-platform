from app.models.user import User
from app.security.dependencies import require_admin
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session
from decimal import Decimal

from app.db.database import get_db
from app.schemas.product import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from app.services.product_service import (
    ProductAlreadyExistsError,
    ProductNotFoundError,
    create_product,
    delete_product,
    get_product_for_read,
    list_products,
    update_product,
)


router = APIRouter(
    prefix="/products",
    tags=["Products"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]
AdminUser = Annotated[
    User,
    Depends(require_admin),
]

@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_product_endpoint(
    product_data: ProductCreate,
    database_session: DatabaseSession,
    current_admin: AdminUser,
) -> ProductResponse:
    try:
        return create_product(
            database_session=database_session,
            product_data=product_data,
        )
    except ProductAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error



@router.get(
    "",
    response_model=list[ProductResponse],
)
def list_products_endpoint(
    database_session: DatabaseSession,
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    min_price: Decimal | None = Query(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
        allow_inf_nan=False,
    ),
    max_price: Decimal | None = Query(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
        allow_inf_nan=False,
    ),
    q: str | None = Query(
        default=None,
        min_length=1,
        max_length=100,
        description="Search product name, description, or SKU",
    ),
) -> list[ProductResponse]:
    if q is not None:
        q = q.strip()

        if not q:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="q must contain at least one non-whitespace character",
            )

    if (
        min_price is not None
        and max_price is not None
        and min_price > max_price
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="min_price must be less than or equal to max_price",
        )

    return list_products(
        database_session=database_session,
        skip=skip,
        limit=limit,
        min_price=min_price,
        max_price=max_price,
        q=q,
    )


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
)
def get_product_endpoint(
    product_id: int,
    database_session: DatabaseSession,
) -> ProductResponse:
    try:
        return get_product_for_read(
            database_session=database_session,
            product_id=product_id,
        )
    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
)
def update_product_endpoint(
    product_id: int,
    product_data: ProductUpdate,
    database_session: DatabaseSession,
    current_admin: AdminUser,
) -> ProductResponse:
    try:
        return update_product(
            database_session=database_session,
            product_id=product_id,
            product_data=product_data,
        )
    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product_endpoint(
    product_id: int,
    database_session: DatabaseSession,
    current_admin: AdminUser,
) -> Response:
    try:
        delete_product(
            database_session=database_session,
            product_id=product_id,
        )
    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )