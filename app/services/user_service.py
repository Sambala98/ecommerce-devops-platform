from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.schemas.user import UserCreate
from app.security.password import hash_password, verify_password


class UserAlreadyExistsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


def create_user(
    db: Session,
    user_data: UserCreate,
) -> User:
    user = User(
        email=user_data.email,
        name=user_data.name,
        hashed_password=hash_password(
            user_data.password
        ),
        role=UserRole.USER,
    )

    db.add(user)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()

        raise UserAlreadyExistsError(
            f"User with email {user_data.email} already exists"
        ) from error

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

def get_user_by_email(
    db: Session,
    email: str,
) -> User | None:
    result = db.execute(
        select(User).where(User.email == email)
    )

    return result.scalar_one_or_none()


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> User | None:
    user = get_user_by_email(
        db,
        email,
    )

    if user is None:
        return None

    if user.hashed_password == "!legacy-no-password!":
        return None

    if not verify_password(
        password,
        user.hashed_password,
    ):
        return None

    return user