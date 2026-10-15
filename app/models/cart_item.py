from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class CartItem(Base):
    __tablename__ = "cart_items"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "product_id",
            name="uq_cart_items_user_product",
        ),
        CheckConstraint(
            "quantity > 0 AND quantity <= 1000000",
            name="ck_cart_items_quantity_range",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )