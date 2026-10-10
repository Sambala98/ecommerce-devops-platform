"""Add persistent cart items."""

from alembic import op
import sqlalchemy as sa


revision = "cart_items_v1"
down_revision = "order_placed_event_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cart_items",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey(
                "products.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "product_id",
            name="uq_cart_items_user_product",
        ),
        sa.CheckConstraint(
            "quantity > 0 AND quantity <= 1000000",
            name="ck_cart_items_quantity_range",
        ),
    )

    op.create_index(
        "ix_cart_items_product_id",
        "cart_items",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cart_items_product_id",
        table_name="cart_items",
    )

    op.drop_table("cart_items")