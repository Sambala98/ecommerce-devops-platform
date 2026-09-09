from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate


class UserAlreadyExistsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


def create_user(db: Session, user_data: UserCreate) -> User:
    user = User(
        email=user_data.email,
        name=user_data.name,
    )

    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise UserAlreadyExistsError(
            f"User with email {user_data.email} already exists"
        )

    db.refresh(user)

    return user


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)

    if user is None:
        raise UserNotFoundError(
            f"User {user_id} not found"
        )

    return user


def get_users(db: Session) -> list[User]:
    result = db.execute(
        select(User).order_by(User.id)
    )

    return list(result.scalars().all())