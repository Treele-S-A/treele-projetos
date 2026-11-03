"""Cronograma de projetos em Gantt (PRO-FL-001)

Um cronograma por obra, as atividades (fase, duração em dias úteis, progresso)
e os vínculos entre elas (TI, II, TT, com defasagem).

Revision ID: e2b4d6f8a0c3
Revises: d1f3b5c7e9a2
Create Date: 2026-11-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2b4d6f8a0c3"
down_revision: Union[str, Sequence[str], None] = "d1f3b5c7e9a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cronogramas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("obra_id", sa.Integer(), sa.ForeignKey("obras.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("inicio", sa.Date(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_por_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_table(
        "cronograma_atividades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cronograma_id", sa.Integer(),
                  sa.ForeignKey("cronogramas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("fase", sa.String(120), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("area", sa.String(60), nullable=True),
        sa.Column("responsavel", sa.String(120), nullable=True),
        sa.Column("duracao", sa.Integer(), nullable=False),
        sa.Column("inicio_fixo", sa.Date(), nullable=True),
        sa.Column("progresso", sa.Integer(), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
    )
    op.create_index("ix_cronograma_atividades_cronograma_id", "cronograma_atividades", ["cronograma_id"])
    op.create_table(
        "cronograma_vinculos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("predecessora_id", sa.Integer(),
                  sa.ForeignKey("cronograma_atividades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sucessora_id", sa.Integer(),
                  sa.ForeignKey("cronograma_atividades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(2), nullable=False),
        sa.Column("defasagem", sa.Integer(), nullable=False),
        sa.UniqueConstraint("predecessora_id", "sucessora_id", name="uq_cronograma_vinculo"),
    )
    op.create_index("ix_cronograma_vinculos_predecessora_id", "cronograma_vinculos", ["predecessora_id"])
    op.create_index("ix_cronograma_vinculos_sucessora_id", "cronograma_vinculos", ["sucessora_id"])


def downgrade() -> None:
    op.drop_index("ix_cronograma_vinculos_sucessora_id", table_name="cronograma_vinculos")
    op.drop_index("ix_cronograma_vinculos_predecessora_id", table_name="cronograma_vinculos")
    op.drop_table("cronograma_vinculos")
    op.drop_index("ix_cronograma_atividades_cronograma_id", table_name="cronograma_atividades")
    op.drop_table("cronograma_atividades")
    op.drop_table("cronogramas")
