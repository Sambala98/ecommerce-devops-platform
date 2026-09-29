"""Add reserved inventory."""

from alembic import op
import sqlalchemy as sa


revision = "inv_reservations_v1"
down_revision = "d4470ea87199"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "reserved_quantity",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # Available stock was already deducted by the old application.
    # Backfill only the reservation counter.
    op.execute(
        """
        UPDATE products AS p
        SET reserved_quantity = reservations.quantity
        FROM (
            SELECT
                oi.product_id,
                SUM(oi.quantity) AS quantity
            FROM order_items AS oi
            JOIN orders AS o ON o.id = oi.order_id
            WHERE o.status IN ('PENDING', 'CONFIRMED')
            GROUP BY oi.product_id
        ) AS reservations
        WHERE p.id = reservations.product_id
        """
    )

    op.create_check_constraint(
        "ck_products_stock_nonnegative",
        "products",
        "stock_quantity >= 0",
    )

    op.create_check_constraint(
        "ck_products_reserved_nonnegative",
        "products",
        "reserved_quantity >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_products_reserved_nonnegative",
        "products",
        type_="check",
    )

    op.drop_constraint(
        "ck_products_stock_nonnegative",
        "products",
        type_="check",
    )

    op.drop_column("products", "reserved_quantity")