from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.cart import (
    CartItemResponse,
    CartItemSetRequest,
)
from app.security.dependencies import get_current_user
from app.services.cart_service import (
    CartProductInactiveError,
    CartProductNotFoundError,
    get_cart,
    remove_cart_item,
    set_cart_item,
)


router = APIRouter(
    prefix="/cart",
    tags=["Cart"],
)

DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
ProductId = Annotated[int, Path(gt=0)]


@router.get(
    "",
    response_model=list[CartItemResponse],
)
def get_cart_endpoint(
    db: DatabaseSession,
    current_user: CurrentUser,
):
    return get_cart(
        db=db,
        user_id=current_user.id,
    )


@router.put(
    "/items/{product_id}",
    response_model=CartItemResponse,
    status_code=status.HTTP_200_OK,
)
def set_cart_item_endpoint(
    product_id: ProductId,
    item_data: CartItemSetRequest,
    db: DatabaseSession,
    current_user: CurrentUser,
):
    try:
        return set_cart_item(
            db=db,
            user_id=current_user.id,
            product_id=product_id,
            item_data=item_data,
        )

    except CartProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except CartProductInactiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.delete(
    "/items/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_cart_item_endpoint(
    product_id: ProductId,
    db: DatabaseSession,
    current_user: CurrentUser,
):
    remove_cart_item(
        db=db,
        user_id=current_user.id,
        product_id=product_id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )