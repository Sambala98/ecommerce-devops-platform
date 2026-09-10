from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings


settings = get_settings()


redis_client = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)


def check_redis_connection() -> bool:
    try:
        return bool(redis_client.ping())
    except RedisError:
        return False