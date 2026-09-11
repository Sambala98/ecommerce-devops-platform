from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.interaction import (
    InteractionCreate,
    InteractionResponse,
)
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
    interaction_data: InteractionCreate,
    database_session: DatabaseSession,
) -> InteractionResponse:
    try:
        return create_interaction(
            database_session=database_session,
            interaction_data=interaction_data,
        )

    except InteractionUserNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except InteractionProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error