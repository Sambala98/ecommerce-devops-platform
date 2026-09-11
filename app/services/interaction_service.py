from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_interaction import ProductInteraction
from app.models.user import User
from app.schemas.interaction import InteractionCreate


class InteractionUserNotFoundError(Exception):
    pass


class InteractionProductNotFoundError(Exception):
    pass


def create_interaction(
    database_session: Session,
    interaction_data: InteractionCreate,
) -> ProductInteraction:
    user = database_session.get(
        User,
        interaction_data.user_id,
    )

    if user is None:
        raise InteractionUserNotFoundError(
            f"User with ID {interaction_data.user_id} was not found"
        )

    product = database_session.get(
        Product,
        interaction_data.product_id,
    )

    if product is None:
        raise InteractionProductNotFoundError(
            f"Product with ID {interaction_data.product_id} was not found"
        )

    interaction = ProductInteraction(
        user_id=interaction_data.user_id,
        product_id=interaction_data.product_id,
        interaction_type=interaction_data.interaction_type,
    )

    database_session.add(interaction)
    database_session.commit()
    database_session.refresh(interaction)

    return interaction