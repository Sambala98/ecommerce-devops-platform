from decimal import Decimal

import pytest

from app.models.product import Product


@pytest.fixture
def priced_products(database_session):
    # Deliberately not sorted by price.
    prices = ["10.00", "50.00", "20.00", "75.00", "35.00"]
    products = []

    for index, price in enumerate(prices):
        product = Product(
            name=f"Filter Product {index}",
            sku=f"FILTER-{index:03d}",
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
    "params, expected_indexes",
    [
        pytest.param({}, [0, 1, 2, 3, 4], id="no-filters"),
        pytest.param(
            {"min_price": "35.00"},
            [1, 3, 4],
            id="minimum-inclusive",
        ),
        pytest.param(
            {"max_price": "20.00"},
            [0, 2],
            id="maximum-inclusive",
        ),
        pytest.param(
            {"min_price": "20.00", "max_price": "50.00"},
            [1, 2, 4],
            id="both-boundaries-inclusive",
        ),
        pytest.param(
            {"min_price": "35.00", "max_price": "35.00"},
            [4],
            id="exact-price",
        ),
        pytest.param(
            {"min_price": "80.00"},
            [],
            id="no-matches",
        ),
        pytest.param(
            {"max_price": "0"},
            [],
            id="zero-is-valid-filter",
        ),
    ],
)
def test_price_filters(
    client,
    priced_products,
    params,
    expected_indexes,
):
    # No authorization header: catalog reads remain public.
    response = client.get("/products", params=params)

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)

    expected = [priced_products[i] for i in expected_indexes]

    assert [item["id"] for item in body] == [
        product.id for product in expected
    ]
    assert [Decimal(item["price"]) for item in body] == [
        product.price for product in expected
    ]


def test_price_filter_runs_before_pagination(
    client,
    priced_products,
):
    params = {
        "min_price": "20.00",
        "max_price": "50.00",
        "limit": 1,
    }

    # Matching products, in ID order: indexes 1, 2, 4.
    for skip, expected_index in enumerate([1, 2, 4]):
        response = client.get(
            "/products",
            params={**params, "skip": skip},
        )

        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()] == [
            priced_products[expected_index].id
        ]

    exhausted = client.get(
        "/products",
        params={**params, "skip": 3},
    )
    assert exhausted.status_code == 200, exhausted.text
    assert exhausted.json() == []


def test_reversed_price_range_returns_422(client):
    response = client.get(
        "/products",
        params={
            "min_price": "50.00",
            "max_price": "20.00",
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == (
        "min_price must be less than or equal to max_price"
    )


@pytest.mark.parametrize("field", ["min_price", "max_price"])
@pytest.mark.parametrize(
    "value",
    [
        "-0.01",
        "12.345",
        "NaN",
        "Infinity",
        "abc",
        "100000000.00",
    ],
)
def test_invalid_price_filter_returns_422(client, field, value):
    response = client.get(
        "/products",
        params={field: value},
    )

    assert response.status_code == 422, response.text
    assert any(
        error["loc"] == ["query", field]
        for error in response.json()["detail"]
    )


@pytest.mark.parametrize(
    "params",
    [
        {"skip": -1},
        {"limit": 0},
        {"limit": 101},
    ],
)
def test_invalid_pagination_returns_422(client, params):
    response = client.get("/products", params=params)

    assert response.status_code == 422, response.text