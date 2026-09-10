import json
import logging
from typing import Any

from redis.exceptions import RedisError

from app.cache.redis_client import redis_client
from app.config import get_settings
from app.models.product import Product


logger = logging.getLogger(__name__) 
settings = get_settings()


def product_cache_key(product_id: int) -> str:
    return f"product:{product_id}"


def get_cached_product(product_id: int) -> dict[str, Any] | None:
    try:
        cached_value = redis_client.get(
            product_cache_key(product_id)
        )

        if cached_value is None:
            return None

        return json.loads(cached_value)

    except (RedisError, json.JSONDecodeError) as error:
      logger.warning(
        "Failed to read product %s from Redis cache: %s",
        product_id,
        error,
    )
    return None

def set_cached_product(product: Product) -> None:
    product_data = {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "sku": product.sku,
        "price": str(product.price),
        "stock_quantity": product.stock_quantity,
        "is_active": product.is_active,
        "created_at": (
            product.created_at.isoformat()
            if product.created_at
            else None
        ),
        "updated_at": (
            product.updated_at.isoformat()
            if product.updated_at
            else None
        ),
    }

    try:
        redis_client.set(
            product_cache_key(product.id),
            json.dumps(product_data),
            ex=settings.redis_cache_ttl,
        )
    except RedisError as error:
       logger.warning(
        "Failed to cache product %s in Redis: %s",
        product.id,
        error,
    )

def invalidate_product_cache(product_id: int) -> None:
    try:
        redis_client.delete(
            product_cache_key(product_id)
        )
    except RedisError as error:
     logger.warning(
        "Failed to invalidate Redis cache for product %s: %s",
        product_id,
        error,
    )