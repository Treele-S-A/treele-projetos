"""Endereço da obra

Vai na ata de análise crítica (ENG-FL-001). Obrigatório ao criar obra nova;
as já cadastradas ficam vazias até alguém preencher nas configurações.

Revision ID: a7c9e1b3d5f8
Revises: f6a8c0e2b4d6
Create Date: 2026-10-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c9e1b3d5f8"
down_revision: Union[str, Sequence[str], None] = "f6a8c0e2b4d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("obras", sa.Column("endereco", sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column("obras", "endereco")
