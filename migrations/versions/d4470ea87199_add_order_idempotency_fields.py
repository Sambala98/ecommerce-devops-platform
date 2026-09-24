"""Add order idempotency fields

Revision ID: d4470ea87199
Revises: f462430edbbc
Create Date: 2026-09-22 12:18:08.313351

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4470ea87199'
down_revision: Union[str, Sequence[str], None] = 'f462430edbbc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "idempotency_key",
            sa.String(length=128),
            nullable=True,
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "idempotency_request_hash",
            sa.String(length=64),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        "uq_orders_user_id_idempotency_key",
        "orders",
        ["user_id", "idempotency_key"],
    )

    op.create_check_constraint(
        "ck_orders_idempotency_fields_paired",
        "orders",
        """
        (
            idempotency_key IS NULL
            AND idempotency_request_hash IS NULL
        )
        OR
        (
            idempotency_key IS NOT NULL
            AND idempotency_request_hash IS NOT NULL
        )
        """,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_orders_idempotency_fields_paired",
        "orders",
        type_="check",
    )

    op.drop_constraint(
        "uq_orders_user_id_idempotency_key",
        "orders",
        type_="unique",
    )

    op.drop_column(
        "orders",
        "idempotency_request_hash",
    )

    op.drop_column(
        "orders",
        "idempotency_key",
    )
