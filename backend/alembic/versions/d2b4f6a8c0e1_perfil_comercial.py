"""Perfil comercial

Usuário global, como o administrador, mas no extremo oposto: enxerga todas as
obras sem participar de nenhuma equipe, e só os documentos da disciplina COM
liberados para obra — para baixar. Nada mais.

Revision ID: d2b4f6a8c0e1
Revises: c0a1d3e5f7b9
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2b4f6a8c0e1"
down_revision: Union[str, Sequence[str], None] = "c0a1d3e5f7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("comercial", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_column("comercial")
