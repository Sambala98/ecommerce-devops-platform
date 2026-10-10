from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CartItemSetRequest(BaseModel):
    quantity: int = Field(
        strict=True,
        gt=0,
        le=1_000_000,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class CartItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )