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
    def allow_client_interactions_only(
        cls,
        value: InteractionType,
    ) -> InteractionType:
        allowed_types = {
            InteractionType.VIEW,
            InteractionType.ADD_TO_CART,
        }

        if value not in allowed_types:
            raise ValueError(
                "Only VIEW and ADD_TO_CART interactions "
                "can be submitted manually"
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