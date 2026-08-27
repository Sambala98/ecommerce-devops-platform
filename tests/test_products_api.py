def test_create_product(client):
    response = client.post(
        "/products",
        json={
            "name": "Wireless Mouse",
            "description": "Ergonomic wireless mouse",
            "sku": "TEST-MOUSE-001",
            "price": "29.99",
            "stock_quantity": 50,
            "is_active": True,
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == "Wireless Mouse"
    assert data["sku"] == "TEST-MOUSE-001"
    assert data["stock_quantity"] == 50
    assert data["id"] is not None


def test_get_product(client):
    create_response = client.post(
        "/products",
        json={
            "name": "Mechanical Keyboard",
            "description": "Mechanical keyboard",
            "sku": "TEST-KEYBOARD-001",
            "price": "89.99",
            "stock_quantity": 25,
            "is_active": True,
        },
    )

    product_id = create_response.json()["id"]

    response = client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 200
    assert response.json()["sku"] == "TEST-KEYBOARD-001"


def test_missing_product_returns_404(client):
    response = client.get("/products/999999")

    assert response.status_code == 404

def test_duplicate_sku_returns_409(client):
    payload = {
        "name": "Wireless Mouse",
        "description": "Test mouse",
        "sku": "DUPLICATE-SKU-001",
        "price": "29.99",
        "stock_quantity": 10,
        "is_active": True,
    }

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
        json={
            "name": "Laptop Stand",
            "description": "Adjustable stand",
            "sku": "TEST-STAND-001",
            "price": "39.99",
            "stock_quantity": 15,
            "is_active": True,
        },
    )

    product_id = create_response.json()["id"]

    response = client.patch(
        f"/products/{product_id}",
        json={
            "price": "34.99",
            "stock_quantity": 20,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["price"] == "34.99"
    assert data["stock_quantity"] == 20

def test_delete_product(client):
    create_response = client.post(
        "/products",
        json={
            "name": "USB-C Hub",
            "description": "Multi-port USB-C hub",
            "sku": "TEST-HUB-001",
            "price": "49.99",
            "stock_quantity": 30,
            "is_active": True,
        },
    )

    product_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/products/{product_id}"
    )

    assert delete_response.status_code == 204

    get_response = client.get(
        f"/products/{product_id}"
    )

    assert get_response.status_code == 404