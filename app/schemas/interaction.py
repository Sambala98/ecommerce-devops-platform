from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.product_interaction import InteractionType


class InteractionCreateRequest(BaseModel):
    product_id: int
    interaction_type: InteractionType

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator("interaction_type")
    @classmethod
    def reject_manual_purchase(
        cls,
        value: InteractionType,
    ) -> InteractionType:
        if value == InteractionType.PURCHASE:
            raise ValueError(
                "PURCHASE interactions are created automatically through orders"
            )

        return value


class InteractionCreate(InteractionCreateRequest):
    user_id: int


class InteractionResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    interaction_type: InteractionType
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )