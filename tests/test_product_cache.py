from decimal import Decimal

from sqlalchemy import select

from app.models.product import Product


PRODUCT_DATA = {
    "name": "Redis Test Keyboard",
    "description": "Product used for Redis cache testing",
    "sku": "REDIS-KEYBOARD-001",
    "price": 49.99,
    "stock_quantity": 20,
    "is_active": True,
}


def create_test_product(
    client,
    admin_headers,
):
    response = client.post(
        "/products",
        headers=admin_headers,
        json=PRODUCT_DATA,
    )

    assert response.status_code == 201

    return response.json()


def test_get_product_populates_cache(
    client,
    admin_headers,
    redis_test_client,
):
    product = create_test_product(
        client,
        admin_headers,
    )

    product_id = product["id"]

    cache_key = f"product:{product_id}"

    assert (
        redis_test_client.get(cache_key)
        is None
    )

    response = client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 200

    cached_product = redis_test_client.get(
        cache_key
    )

    assert cached_product is not None


def test_cached_product_has_ttl(
    client,
    admin_headers,
    redis_test_client,
):
    product = create_test_product(
        client,
        admin_headers,
    )

    product_id = product["id"]

    response = client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 200

    ttl = redis_test_client.ttl(
        f"product:{product_id}"
    )

    assert 0 < ttl <= 300


def test_cached_product_can_be_read_from_cache(
    client,
    database_session,
    admin_headers,
    redis_test_client,
):
    product = create_test_product(
        client,
        admin_headers,
    )

    product_id = product["id"]

    first_response = client.get(
        f"/products/{product_id}"
    )

    assert first_response.status_code == 200

    cache_key = f"product:{product_id}"

    assert (
        redis_test_client.get(cache_key)
        is not None
    )

    # Remove the row directly from PostgreSQL without
    # going through the API. This deliberately leaves
    # the Redis cache untouched.
    db_product = database_session.get(
        Product,
        product_id,
    )

    database_session.delete(db_product)
    database_session.commit()

    second_response = client.get(
        f"/products/{product_id}"
    )

    assert second_response.status_code == 200

    data = second_response.json()

    assert data["id"] == product_id
    assert data["sku"] == PRODUCT_DATA["sku"]


def test_patch_invalidates_product_cache(
    client,
    admin_headers,
    redis_test_client,
):
    product = create_test_product(
        client,
        admin_headers,
    )

    product_id = product["id"]

    client.get(
        f"/products/{product_id}"
    )

    cache_key = f"product:{product_id}"

    assert (
        redis_test_client.get(cache_key)
        is not None
    )

    response = client.patch(
        f"/products/{product_id}",
        headers=admin_headers,
        json={
            "price": 59.99,
        },
    )

    assert response.status_code == 200

    assert (
        redis_test_client.get(cache_key)
        is None
    )


def test_patch_returns_fresh_value_after_invalidation(
    client,
    admin_headers,
    redis_test_client,
):
    product = create_test_product(
        client,
        admin_headers,
    )

    product_id = product["id"]

    first_get = client.get(
        f"/products/{product_id}"
    )

    assert first_get.status_code == 200

    update_response = client.patch(
        f"/products/{product_id}",
        headers=admin_headers,
        json={
            "price": 59.99,
        },
    )

    assert update_response.status_code == 200

    second_get = client.get(
        f"/products/{product_id}"
    )

    assert second_get.status_code == 200

    assert (
        Decimal(
            str(
                second_get.json()["price"]
            )
        )
        == Decimal("59.99")
    )


def test_delete_invalidates_product_cache(
    client,
    admin_headers,
    redis_test_client,
):
    product = create_test_product(
        client,
        admin_headers,
    )

    product_id = product["id"]

    client.get(
        f"/products/{product_id}"
    )

    cache_key = f"product:{product_id}"

    assert (
        redis_test_client.get(cache_key)
        is not None
    )

    response = client.delete(
        f"/products/{product_id}",
        headers=admin_headers,
    )

    assert response.status_code == 204

    assert (
        redis_test_client.get(cache_key)
        is None
    )


def test_deleted_product_is_not_returned_from_stale_cache(
    client,
    admin_headers,
    redis_test_client,
):
    product = create_test_product(
        client,
        admin_headers,
    )

    product_id = product["id"]

    first_get = client.get(
        f"/products/{product_id}"
    )

    assert first_get.status_code == 200

    delete_response = client.delete(
        f"/products/{product_id}",
        headers=admin_headers,
    )

    assert delete_response.status_code == 204

    response = client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 404


def test_get_product_falls_back_when_redis_fails(
    client,
    admin_headers,
):
    """
    This test intentionally does NOT request
    redis_test_client.

    conftest.py supplies UnavailableRedis, so
    Redis fails and the API must fall back to
    PostgreSQL.
    """

    product = create_test_product(
        client,
        admin_headers,
    )

    product_id = product["id"]

    response = client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == product_id


def test_patch_succeeds_when_cache_invalidation_fails(
    client,
    admin_headers,
):
    """
    Redis is deliberately unavailable here.
    PostgreSQL remains the source of truth.
    """

    product = create_test_product(
        client,
        admin_headers,
    )

    product_id = product["id"]

    response = client.patch(
        f"/products/{product_id}",
        headers=admin_headers,
        json={
            "price": 69.99,
        },
    )

    assert response.status_code == 200

    assert (
        Decimal(
            str(
                response.json()["price"]
            )
        )
        == Decimal("69.99")
    )


def test_database_contains_updated_value_when_redis_fails(
    client,
    database_session,
    admin_headers,
):
    product = create_test_product(
        client,
        admin_headers,
    )

    product_id = product["id"]

    response = client.patch(
        f"/products/{product_id}",
        headers=admin_headers,
        json={
            "price": 74.99,
        },
    )

    assert response.status_code == 200

    database_session.expire_all()

    persisted_product = (
        database_session.execute(
            select(Product).where(
                Product.id == product_id
            )
        )
        .scalar_one()
    )

    assert (
        persisted_product.price
        == Decimal("74.99")
    )