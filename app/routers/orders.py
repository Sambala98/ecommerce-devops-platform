from app.models.user import User, UserRole
from app.security.dependencies import (
    get_current_user,
    require_admin,
)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.order import (
    OrderCreate,
    OrderCreateRequest,
    OrderResponse,
    OrderStatusUpdate,
)
from app.services.order_service import (
    EmptyOrderError,
    InsufficientStockError,
    InvalidOrderStatusTransitionError,
    OrderNotFoundError,
    ProductNotFoundError,
    UserNotFoundError,
    create_order,
    get_order,
    get_orders,
    update_order_status,
    get_orders_for_user,
)


router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)



@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_order_endpoint(
    order_data: OrderCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service_order_data = OrderCreate(
        user_id=current_user.id,
        items=order_data.items,
    )

    try:
        return create_order(
            db,
            service_order_data,
        )

    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InsufficientStockError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except EmptyOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

@router.get(
    "",
    response_model=list[OrderResponse],
)
def list_orders_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == UserRole.ADMIN:
        return get_orders(db)

    return get_orders_for_user(
        db=db,
        user_id=current_user.id,
    )


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
)
def get_order_endpoint(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = get_order(
        db,
        order_id,
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )

    if (
        current_user.role != UserRole.ADMIN
        and order.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this order",
        )

    return order

@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
)
def update_order_status_endpoint(
    order_id: int,
    status_data: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    try:
        return update_order_status(
            db=db,
            order_id=order_id,
            status_data=status_data,
        )

    except OrderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InvalidOrderStatusTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
