from decimal import Decimal


def product_payload(
    sku: str = "MOUSE-001",
):
    return {
        "name": "Wireless Mouse",
        "description": "Test product",
        "sku": sku,
        "price": 19.99,
        "stock_quantity": 10,
        "is_active": True,
    }


def test_create_product_requires_authentication(
    client,
):
    response = client.post(
        "/products",
        json=product_payload(),
    )

    assert response.status_code == 401


def test_normal_user_cannot_create_product(
    client,
    user_headers,
):
    response = client.post(
        "/products",
        headers=user_headers,
        json=product_payload(),
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]
        == "Admin access required"
    )


def test_admin_can_create_product(
    client,
    admin_headers,
):
    response = client.post(
        "/products",
        headers=admin_headers,
        json=product_payload(),
    )

    assert response.status_code == 201

    body = response.json()

    assert body["name"] == "Wireless Mouse"
    assert body["sku"] == "MOUSE-001"
    assert float(body["price"]) == 19.99
    assert body["stock_quantity"] == 10
    assert body["is_active"] is True


def test_get_product_is_public(
    client,
    admin_headers,
):
    create_response = client.post(
        "/products",
        headers=admin_headers,
        json=product_payload(),
    )

    assert create_response.status_code == 201

    product_id = create_response.json()["id"]

    response = client.get(
        f"/products/{product_id}",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == product_id
    assert body["sku"] == "MOUSE-001"


def test_list_products_is_public(
    client,
    admin_headers,
):
    first_response = client.post(
        "/products",
        headers=admin_headers,
        json=product_payload(
            sku="MOUSE-001",
        ),
    )

    second_response = client.post(
        "/products",
        headers=admin_headers,
        json=product_payload(
            sku="MOUSE-002",
        ),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = client.get(
        "/products",
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 2


def test_duplicate_sku_returns_409(
    client,
    admin_headers,
):
    payload = product_payload()

    first_response = client.post(
        "/products",
        headers=admin_headers,
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/products",
        headers=admin_headers,
        json=payload,
    )

    assert second_response.status_code == 409


def test_normal_user_cannot_update_product(
    client,
    admin_headers,
    user_headers,
):
    create_response = client.post(
        "/products",
        headers=admin_headers,
        json=product_payload(),
    )

    product_id = create_response.json()["id"]

    response = client.patch(
        f"/products/{product_id}",
        headers=user_headers,
        json={
            "price": 24.99,
        },
    )

    assert response.status_code == 403


def test_admin_can_update_product(
    client,
    admin_headers,
):
    create_response = client.post(
        "/products",
        headers=admin_headers,
        json=product_payload(),
    )

    assert create_response.status_code == 201

    product_id = create_response.json()["id"]

    response = client.patch(
        f"/products/{product_id}",
        headers=admin_headers,
        json={
            "price": 24.99,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert float(body["price"]) == 24.99


def test_normal_user_cannot_delete_product(
    client,
    admin_headers,
    user_headers,
):
    create_response = client.post(
        "/products",
        headers=admin_headers,
        json=product_payload(),
    )

    product_id = create_response.json()["id"]

    response = client.delete(
        f"/products/{product_id}",
        headers=user_headers,
    )

    assert response.status_code == 403


def test_admin_can_delete_product(
    client,
    admin_headers,
):
    create_response = client.post(
        "/products",
        headers=admin_headers,
        json=product_payload(),
    )

    assert create_response.status_code == 201

    product_id = create_response.json()["id"]

    response = client.delete(
        f"/products/{product_id}",
        headers=admin_headers,
    )

    assert response.status_code == 204

    get_response = client.get(
        f"/products/{product_id}",
    )

    assert get_response.status_code == 404


def test_get_missing_product_returns_404(
    client,
):
    response = client.get(
        "/products/999999",
    )

    assert response.status_code == 404


def test_admin_update_missing_product_returns_404(
    client,
    admin_headers,
):
    response = client.patch(
        "/products/999999",
        headers=admin_headers,
        json={
            "price": 29.99,
        },
    )

    assert response.status_code == 404