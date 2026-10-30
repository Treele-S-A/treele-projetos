"""Usuário "todas as obras"

Tipo de acesso: papel "obra" em todas as obras, inclusive as criadas depois.

Revision ID: c9e1a3b5d7f0
Revises: b8d0f2a4c6e9
Create Date: 2026-10-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9e1a3b5d7f0"
down_revision: Union[str, Sequence[str], None] = "b8d0f2a4c6e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("todas_obras", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("usuarios", "todas_obras")
