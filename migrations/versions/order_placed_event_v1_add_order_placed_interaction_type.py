"""Add order placed interaction type

Revision ID: order_placed_event_v1
Revises: inv_reservations_v1
Create Date: 2026-10-07 14:10:10.849337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'order_placed_event_v1'
down_revision: Union[str, Sequence[str], None] = 'inv_reservations_v1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TYPE interactiontype
        ADD VALUE IF NOT EXISTS 'ORDER_PLACED'
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Removing ORDER_PLACED requires a separate migration "
        "that handles existing event rows and rebuilds the enum."
    )