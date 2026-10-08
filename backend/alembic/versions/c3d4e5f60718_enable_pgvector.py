"""enable pgvector

Revision ID: c3d4e5f60718
Revises: 601a0c533a81
Create Date: 2026-10-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f60718'
down_revision: Union[str, Sequence[str], None] = '601a0c533a81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
