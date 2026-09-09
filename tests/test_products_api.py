from decimal import Decimal


def product_payload(
    sku="MOUSE-TEST-001",
    stock_quantity=10,
):
    return {
        "name": "Test Mouse",
        "description": "Product API test",
        "sku": sku,
        "price": 29.99,
        "stock_quantity": stock_quantity,
        "is_active": True,
    }


def test_create_product(client):
    response = client.post(
        "/products",
        json=product_payload(),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == "Test Mouse"
    assert data["sku"] == "MOUSE-TEST-001"
    assert Decimal(str(data["price"])) == Decimal("29.99")
    assert data["stock_quantity"] == 10
    assert "id" in data


def test_get_product(client):
    create_response = client.post(
        "/products",
        json=product_payload(),
    )

    assert create_response.status_code == 201

    product_id = create_response.json()["id"]

    response = client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == product_id
    assert data["sku"] == "MOUSE-TEST-001"


def test_missing_product_returns_404(client):
    response = client.get(
        "/products/999999"
    )

    assert response.status_code == 404


def test_duplicate_sku_returns_409(client):
    payload = product_payload()

    first_response = client.post(
        "/products",
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/products",
        json=payload,
    )

    assert second_response.status_code == 409


def test_update_product(client):
    create_response = client.post(
        "/products",
        json=product_payload(),
    )

    product_id = create_response.json()["id"]

    response = client.patch(
        f"/products/{product_id}",
        json={
            "price": 39.99,
            "stock_quantity": 20,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert Decimal(str(data["price"])) == Decimal("39.99")
    assert data["stock_quantity"] == 20


def test_delete_product(client):
    create_response = client.post(
        "/products",
        json=product_payload(),
    )

    product_id = create_response.json()["id"]

    response = client.delete(
        f"/products/{product_id}"
    )

    assert response.status_code == 204

    get_response = client.get(
        f"/products/{product_id}"
    )

    assert get_response.status_code == 404