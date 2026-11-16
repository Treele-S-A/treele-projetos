"""Conflitos do 3D no pedido de revisão, na reprovação e na ata

Um pedido (ou reprovação) trata vários conflitos; a ata da revisão que traz a
correção guarda o retrato deles no dia.

Revision ID: a2c4e6b8d0f1
Revises: f3c5e7a9b1d4
Create Date: 2026-11-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2c4e6b8d0f1"
down_revision: Union[str, Sequence[str], None] = "f3c5e7a9b1d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conflitos_solicitacao",
        sa.Column("solicitacao_id", sa.Integer(),
                  sa.ForeignKey("solicitacoes_revisao.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("conflito_id", sa.Integer(),
                  sa.ForeignKey("conflitos.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_conflitos_solicitacao_conflito_id", "conflitos_solicitacao", ["conflito_id"])
    op.create_table(
        "conflitos_reprovacao",
        sa.Column("revisao_id", sa.Integer(),
                  sa.ForeignKey("revisoes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("conflito_id", sa.Integer(),
                  sa.ForeignKey("conflitos.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_conflitos_reprovacao_conflito_id", "conflitos_reprovacao", ["conflito_id"])
    with op.batch_alter_table("atas_analise") as t:
        t.add_column(sa.Column("conflitos", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("atas_analise") as t:
        t.drop_column("conflitos")
    op.drop_index("ix_conflitos_reprovacao_conflito_id", "conflitos_reprovacao")
    op.drop_table("conflitos_reprovacao")
    op.drop_index("ix_conflitos_solicitacao_conflito_id", "conflitos_solicitacao")
    op.drop_table("conflitos_solicitacao")
