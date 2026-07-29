from decimal import Decimal

from app.models.product import Product


def test_product_model_can_be_created() -> None:
    product = Product(
        name="Wireless Mouse",
        description="Ergonomic wireless mouse",
        sku="MOUSE-WIRELESS-001",
        price=Decimal("29.99"),
        stock_quantity=50,
    )

    assert product.name == "Wireless Mouse"
    assert product.sku == "MOUSE-WIRELESS-001"
    assert product.price == Decimal("29.99")
    assert product.stock_quantity == 50


def test_product_description_can_be_none() -> None:
    product = Product(
        name="Mechanical Keyboard",
        description=None,
        sku="KEYBOARD-MECH-001",
        price=Decimal("89.99"),
        stock_quantity=25,
    )

    assert product.description is None