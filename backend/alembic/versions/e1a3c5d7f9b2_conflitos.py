"""Conflitos entre disciplinas guardados no servidor

Conjuntos de teste da obra (compartilhados pela equipe), as rodadas de
detecção e os conflitos, com situação (novo, ativo, aprovado, resolvido)
reconhecida entre revisões pelos GlobalIds.

Revision ID: e1a3c5d7f9b2
Revises: c3e5a7b9d1f4
Create Date: 2026-10-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1a3c5d7f9b2"
down_revision: Union[str, Sequence[str], None] = "c3e5a7b9d1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conjuntos_conflito",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("obra_id", sa.Integer(), sa.ForeignKey("obras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("pronto", sa.String(40), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("criado_por_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("obra_id", "pronto", name="uq_conjunto_pronto"),
    )
    op.create_index("ix_conjuntos_conflito_obra_id", "conjuntos_conflito", ["obra_id"])
    op.create_table(
        "rodadas_conflito",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conjunto_id", sa.Integer(),
                  sa.ForeignKey("conjuntos_conflito.id", ondelete="CASCADE"), nullable=False),
        sa.Column("arquivos", sa.JSON(), nullable=False),
        sa.Column("encontrados", sa.Integer(), nullable=False),
        sa.Column("novos", sa.Integer(), nullable=False),
        sa.Column("reabertos", sa.Integer(), nullable=False),
        sa.Column("resolvidos", sa.Integer(), nullable=False),
        sa.Column("feita_por_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feita_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rodadas_conflito_conjunto_id", "rodadas_conflito", ["conjunto_id"])
    op.create_table(
        "conflitos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conjunto_id", sa.Integer(),
                  sa.ForeignKey("conjuntos_conflito.id", ondelete="CASCADE"), nullable=False),
        sa.Column("obra_id", sa.Integer(), sa.ForeignKey("obras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("tipo", sa.String(14), nullable=False),
        sa.Column("documento_a_id", sa.Integer(),
                  sa.ForeignKey("documentos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("documento_b_id", sa.Integer(),
                  sa.ForeignKey("documentos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revisao_a", sa.String(10), nullable=False),
        sa.Column("revisao_b", sa.String(10), nullable=False),
        sa.Column("categoria_a", sa.String(60), nullable=False),
        sa.Column("categoria_b", sa.String(60), nullable=False),
        sa.Column("nome_a", sa.String(300), nullable=True),
        sa.Column("nome_b", sa.String(300), nullable=True),
        sa.Column("guids_a", sa.JSON(), nullable=False),
        sa.Column("guid_b", sa.String(40), nullable=False),
        sa.Column("centro", sa.JSON(), nullable=False),
        sa.Column("caixa", sa.JSON(), nullable=False),
        sa.Column("medida", sa.Float(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visto_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vista_id", sa.Integer(),
                  sa.ForeignKey("vistas_modelo.id", ondelete="SET NULL"), nullable=True),
        sa.Column("justificativa", sa.Text(), nullable=True),
        sa.Column("atualizado_por_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_conflitos_conjunto_id", "conflitos", ["conjunto_id"])
    op.create_index("ix_conflitos_obra_id", "conflitos", ["obra_id"])
    op.create_index("ix_conflitos_status", "conflitos", ["status"])
    op.create_index("ix_conflitos_guid_b", "conflitos", ["guid_b"])


def downgrade() -> None:
    op.drop_table("conflitos")
    op.drop_table("rodadas_conflito")
    op.drop_table("conjuntos_conflito")
