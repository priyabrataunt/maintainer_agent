"""create users table

Revision ID: b7c1d2e3f4a5
Revises: 210e466959d9
Create Date: 2026-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1d2e3f4a5'
down_revision: Union[str, Sequence[str], None] = '210e466959d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('github_id', sa.BigInteger(), nullable=False),
    sa.Column('login', sa.String(), nullable=False),
    sa.Column('avatar_url', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('github_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('users')
