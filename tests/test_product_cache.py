from redis.exceptions import RedisError

import app.cache.product_cache as product_cache_module


PRODUCT_DATA = {
    "name": "Redis Test Keyboard",
    "description": "Product used for Redis cache testing",
    "sku": "REDIS-KEYBOARD-001",
    "price": 49.99,
    "stock_quantity": 20,
    "is_active": True,
}


def create_test_product(client):
    response = client.post(
        "/products",
        json=PRODUCT_DATA,
    )

    assert response.status_code == 201

    return response.json()


def test_get_product_populates_cache(
    client,
    redis_test_client,
):
    product = create_test_product(client)
    product_id = product["id"]

    cache_key = f"product:{product_id}"

    assert redis_test_client.get(cache_key) is None

    response = client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 200

    cached_product = redis_test_client.get(cache_key)

    assert cached_product is not None


def test_cached_product_has_ttl(
    client,
    redis_test_client,
):
    product = create_test_product(client)
    product_id = product["id"]

    response = client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 200

    ttl = redis_test_client.ttl(
        f"product:{product_id}"
    )

    assert 0 < ttl <= 300


def test_patch_invalidates_product_cache(
    client,
    redis_test_client,
):
    product = create_test_product(client)
    product_id = product["id"]

    client.get(
        f"/products/{product_id}"
    )

    cache_key = f"product:{product_id}"

    assert redis_test_client.get(cache_key) is not None

    response = client.patch(
        f"/products/{product_id}",
        json={"price": 59.99},
    )

    assert response.status_code == 200
    assert redis_test_client.get(cache_key) is None


def test_delete_invalidates_product_cache(
    client,
    redis_test_client,
):
    product = create_test_product(client)
    product_id = product["id"]

    client.get(
        f"/products/{product_id}"
    )

    cache_key = f"product:{product_id}"

    assert redis_test_client.get(cache_key) is not None

    response = client.delete(
        f"/products/{product_id}"
    )

    assert response.status_code == 204
    assert redis_test_client.get(cache_key) is None


def test_get_product_falls_back_when_redis_fails(
    client,
    monkeypatch,
):
    product = create_test_product(client)
    product_id = product["id"]

    def redis_failure(*args, **kwargs):
        raise RedisError("Redis unavailable")

    monkeypatch.setattr(
        product_cache_module.redis_client,
        "get",
        redis_failure,
    )

    monkeypatch.setattr(
        product_cache_module.redis_client,
        "set",
        redis_failure,
    )

    response = client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == product_id


def test_patch_succeeds_when_cache_invalidation_fails(
    client,
    monkeypatch,
):
    product = create_test_product(client)
    product_id = product["id"]

    def redis_failure(*args, **kwargs):
        raise RedisError("Redis unavailable")

    monkeypatch.setattr(
        product_cache_module.redis_client,
        "delete",
        redis_failure,
    )

    response = client.patch(
        f"/products/{product_id}",
        json={"price": 69.99},
    )

    assert response.status_code == 200
    assert float(response.json()["price"]) == 69.99