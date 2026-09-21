from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class UserRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole),
        default=UserRole.USER,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    orders = relationship(
        "Order",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    interactions = relationship(
        "ProductInteraction",
        back_populates="user",
        cascade="all, delete-orphan",
    )