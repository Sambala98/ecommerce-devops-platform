from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.product_interaction import InteractionType


class InteractionCreate(BaseModel):
    user_id: int
    product_id: int
    interaction_type: InteractionType

    @field_validator("interaction_type")
    @classmethod
    def prevent_manual_purchase(
        cls,
        interaction_type: InteractionType,
    ) -> InteractionType:
        if interaction_type == InteractionType.PURCHASE:
            raise ValueError(
                "PURCHASE interactions are created automatically through orders"
            )

        return interaction_type


class InteractionResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    interaction_type: InteractionType
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )