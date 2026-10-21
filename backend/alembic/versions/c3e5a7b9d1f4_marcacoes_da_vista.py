"""Marcações da vista do modelo 3D em imagem própria

Além da foto marcada, a vista guarda os desenhos em fundo transparente, que o
visualizador põe na cena 3D ao reabrir a vista.

Revision ID: c3e5a7b9d1f4
Revises: b2d4f6a8c0e3
Create Date: 2026-10-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3e5a7b9d1f4"
down_revision: Union[str, Sequence[str], None] = "b2d4f6a8c0e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("vistas_modelo") as t:
        t.add_column(sa.Column("marcacoes_key", sa.String(500), nullable=True))
        t.add_column(sa.Column("marcacoes_tamanho", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("vistas_modelo") as t:
        t.drop_column("marcacoes_tamanho")
        t.drop_column("marcacoes_key")
