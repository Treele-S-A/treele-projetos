"""Análise crítica da revisão

Revisão em revisão é a análise crítica do PBQP-H: o coordenador libera ou
reprova, com observação. A reprovada fica no histórico, com quem e quando.
O status "reprovado" é texto, como os outros — nada a migrar na coluna.

Revision ID: c7e9a1b3d5f7
Revises: b6f8d0e2a4c5
Create Date: 2026-10-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7e9a1b3d5f7"
down_revision: Union[str, Sequence[str], None] = "b6f8d0e2a4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("revisoes") as t:
        t.add_column(sa.Column("observacao", sa.Text(), nullable=True))
        t.add_column(sa.Column("reprovada_em", sa.DateTime(timezone=True), nullable=True))
        t.add_column(sa.Column("reprovada_por_id", sa.Integer(), nullable=True))
        t.create_foreign_key(
            "fk_revisoes_reprovada_por", "usuarios", ["reprovada_por_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("revisoes") as t:
        t.drop_constraint("fk_revisoes_reprovada_por", type_="foreignkey")
        t.drop_column("reprovada_por_id")
        t.drop_column("reprovada_em")
        t.drop_column("observacao")
