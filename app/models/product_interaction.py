from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class InteractionType(str, Enum):
    VIEW = "VIEW"
    ADD_TO_CART = "ADD_TO_CART"
    PURCHASE = "PURCHASE"


class ProductInteraction(Base):
    __tablename__ = "product_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )

    interaction_type: Mapped[InteractionType] = mapped_column(
        SqlEnum(InteractionType),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user = relationship(
        "User",
        back_populates="interactions",
    )

    product = relationship(
        "Product",
    )