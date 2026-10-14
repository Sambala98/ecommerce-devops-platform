"""Add a separate idempotency key for cart checkout."""

from alembic import op
import sqlalchemy as sa


revision = "checkout_key_v1"
down_revision = "cart_items_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "checkout_idempotency_key",
            sa.String(length=128),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        "uq_orders_user_checkout_key",
        "orders",
        ["user_id", "checkout_idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_orders_user_checkout_key",
        "orders",
        type_="unique",
    )

    op.drop_column(
        "orders",
        "checkout_idempotency_key",
    )