from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserResponse
from app.security.dependencies import (
    get_current_user,
    require_admin,
)
from app.services.user_service import (
    UserAlreadyExistsError,
    UserNotFoundError,
    create_user,
    get_user,
    get_users,
)


router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user_endpoint(
    user_data: UserCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return create_user(
            db,
            user_data,
        )

    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[UserResponse],
)
def list_users_endpoint(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_users(db)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user_endpoint(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        requested_user = get_user(
            db,
            user_id,
        )

    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    is_admin = (
        current_user.role
        == UserRole.ADMIN
    )

    is_owner = (
        current_user.id
        == requested_user.id
    )

    if not is_admin and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this user",
        )

    return requested_user