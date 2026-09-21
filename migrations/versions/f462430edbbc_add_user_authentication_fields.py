"""add user authentication fields
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

Revision ID: f462430edbbc
Revises: 25337b8d7d5d
Create Date: 2026-09-15 11:34:01.751134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql



# revision identifiers, used by Alembic.
revision: str = 'f462430edbbc'
down_revision: Union[str, Sequence[str], None] = '25337b8d7d5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None




def upgrade() -> None:
    user_role_enum = postgresql.ENUM(
        "USER",
        "ADMIN",
        name="userrole",
    )

    user_role_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    op.add_column(
        "users",
        sa.Column(
            "hashed_password",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "role",
            user_role_enum,
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE users
        SET hashed_password = '!legacy-no-password!',
            role = 'USER'
        WHERE hashed_password IS NULL
        """
    )

    op.alter_column(
        "users",
        "hashed_password",
        nullable=False,
    )

    op.alter_column(
        "users",
        "role",
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column(
        "users",
        "role",
    )

    op.drop_column(
        "users",
        "hashed_password",
    )

    user_role_enum = postgresql.ENUM(
        "USER",
        "ADMIN",
        name="userrole",
    )

    user_role_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )
