from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError

from app.config import get_settings
from app.models.user import UserRole


settings = get_settings()


def create_access_token(
    user_id: int,
    role: UserRole,
) -> str:
    now = datetime.now(timezone.utc)

    expires_at = now + timedelta(
        minutes=settings.access_token_expire_minutes
    )

    payload = {
        "sub": str(user_id),
        "role": role.value,
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except InvalidTokenError as error:
        raise ValueError(
            "Invalid or expired access token"
        ) from error