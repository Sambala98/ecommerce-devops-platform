from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.interaction import (
    InteractionCreate,
    InteractionCreateRequest,
    InteractionResponse,
)
from app.security.dependencies import get_current_user
from app.services.interaction_service import (
    InteractionProductNotFoundError,
    InteractionUserNotFoundError,
    create_interaction,
)


router = APIRouter(
    prefix="/interactions",
    tags=["Interactions"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "",
    response_model=InteractionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_interaction_endpoint(
    interaction_data: InteractionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service_data = InteractionCreate(
        user_id=current_user.id,
        product_id=interaction_data.product_id,
        interaction_type=interaction_data.interaction_type,
    )

    try:
        return create_interaction(
            db,
            service_data,
        )

    except InteractionUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except InteractionProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc