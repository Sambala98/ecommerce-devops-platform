from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=200,
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
    )
    sku: str = Field(
        min_length=3,
        max_length=100,
    )
    price: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2,
    )
    stock_quantity: int = Field(
        ge=0,
        le=1_000_000,
    )
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
    )
    price: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=2,
    )
    stock_quantity: int | None = Field(
        default=None,
        ge=0,
        le=1_000_000,
    )
    is_active: bool | None = None


class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)