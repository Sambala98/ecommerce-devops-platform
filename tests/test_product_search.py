from decimal import Decimal

import pytest

from app.models.product import Product


@pytest.fixture
def searchable_products(database_session):
    rows = [
        ("Wireless Mouse", None, "MOUSE-001", "20.00"),
        ("Keyboard", "Wireless connection", "KEY-001", "45.00"),
        ("Adapter", None, "WIRELESS-003", "30.00"),
        ("Wireless Headset", None, "HEAD-001", "80.00"),
        ("Discount 50% Cable", None, "USB_A/001", "10.00"),
        ("Discount 500 Cable", None, "USBXA-001", "15.00"),
    ]

    products = []

    for name, description, sku, price in rows:
        product = Product(
            name=name,
            description=description,
            sku=sku,
            price=Decimal(price),
            stock_quantity=10,
            reserved_quantity=0,
            is_active=True,
        )
        database_session.add(product)
        database_session.flush()
        products.append(product)

    database_session.commit()
    return products


@pytest.mark.parametrize(
    ("query", "expected_indexes"),
    [
        ("mOuSe", [0]),
        ("connection", [1]),
        ("wireless-003", [2]),
        ("WIRELESS", [0, 1, 2, 3]),
        ("  mouse  ", [0]),
        ("50%", [4]),
        ("USB_A", [4]),
        ("/", [4]),
        ("does-not-exist", []),
        ("' OR 1=1 --", []),
    ],
)
def test_public_product_search(
    client,
    searchable_products,
    query,
    expected_indexes,
):
    response = client.get(
        "/products",
        params={"q": query},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        searchable_products[index].id
        for index in expected_indexes
    ]


def test_search_and_price_filters_run_before_pagination(
    client,
    searchable_products,
):
    params = {
        "q": "wireless",
        "min_price": "25.00",
        "max_price": "50.00",
        "limit": 1,
    }

    # Matching products are Keyboard, then Adapter in ID order.
    for skip, expected_index in enumerate([1, 2]):
        response = client.get(
            "/products",
            params={**params, "skip": skip},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [
            searchable_products[expected_index].id
        ]

    response = client.get(
        "/products",
        params={**params, "skip": 2},
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "query",
    ["", "   ", "\t", "a" * 101],
)
def test_invalid_search_returns_422(client, query):
    response = client.get(
        "/products",
        params={"q": query},
    )

    assert response.status_code == 422


def test_search_accepts_100_characters(client):
    response = client.get(
        "/products",
        params={"q": "a" * 100},
    )

    assert response.status_code == 200
    assert response.json() == []