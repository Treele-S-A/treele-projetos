"""Atas de análise crítica (PRO-FL-005)

O checklist respondido antes de liberar para obra, uma ata por liberação de
uma disciplina, com as revisões que ela cobre.

Revision ID: f6a8c0e2b4d6
Revises: e1a3c5d7f9b2
Create Date: 2026-10-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a8c0e2b4d6"
down_revision: Union[str, Sequence[str], None] = "e1a3c5d7f9b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "atas_analise",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("obra_id", sa.Integer(), sa.ForeignKey("obras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("disciplina_id", sa.Integer(), sa.ForeignKey("disciplinas.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("resultado", sa.String(14), nullable=False),
        sa.Column("formulario", sa.String(120), nullable=False),
        sa.Column("itens", sa.JSON(), nullable=False),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("revisoes_texto", sa.JSON(), nullable=False),
        sa.Column("criada_por_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("obra_id", "numero", name="uq_ata_numero"),
    )
    op.create_index("ix_atas_analise_obra_id", "atas_analise", ["obra_id"])
    op.create_table(
        "atas_analise_revisoes",
        sa.Column("ata_id", sa.Integer(),
                  sa.ForeignKey("atas_analise.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revisao_id", sa.Integer(),
                  sa.ForeignKey("revisoes.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_atas_analise_revisoes_revisao_id", "atas_analise_revisoes", ["revisao_id"])


def downgrade() -> None:
    op.drop_index("ix_atas_analise_revisoes_revisao_id", table_name="atas_analise_revisoes")
    op.drop_table("atas_analise_revisoes")
    op.drop_index("ix_atas_analise_obra_id", table_name="atas_analise")
    op.drop_table("atas_analise")
