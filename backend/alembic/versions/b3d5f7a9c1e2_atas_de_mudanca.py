"""Atas de mudança de projeto (módulo Qualidade)

PDFs por obra e disciplina, numerados na ordem em que chegam (SER-HID-AMP01),
cada um com as suas revisões.

Revision ID: b3d5f7a9c1e2
Revises: a2c4e6b8d0f1
Create Date: 2026-11-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3d5f7a9c1e2"
down_revision: Union[str, Sequence[str], None] = "a2c4e6b8d0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "atas_mudanca",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("obra_id", sa.Integer(), sa.ForeignKey("obras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("disciplina_id", sa.Integer(), sa.ForeignKey("disciplinas.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("assunto", sa.String(300), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criada_por_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("obra_id", "disciplina_id", "numero", name="uq_ata_mudanca_numero"),
    )
    op.create_index("ix_atas_mudanca_obra_id", "atas_mudanca", ["obra_id"])
    op.create_table(
        "atas_mudanca_revisoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ata_id", sa.Integer(), sa.ForeignKey("atas_mudanca.id", ondelete="CASCADE"), nullable=True),
        sa.Column("obra_id", sa.Integer(), sa.ForeignKey("obras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("disciplina_id", sa.Integer(), sa.ForeignKey("disciplinas.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=True),
        sa.Column("assunto", sa.String(300), nullable=True),
        sa.Column("nome_original", sa.String(300), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("tamanho", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("enviada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enviada_por_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("ata_id", "numero", name="uq_ata_mudanca_revisao"),
    )
    op.create_index("ix_atas_mudanca_revisoes_ata_id", "atas_mudanca_revisoes", ["ata_id"])
    op.create_index("ix_atas_mudanca_revisoes_obra_id", "atas_mudanca_revisoes", ["obra_id"])


def downgrade() -> None:
    op.drop_index("ix_atas_mudanca_revisoes_obra_id", "atas_mudanca_revisoes")
    op.drop_index("ix_atas_mudanca_revisoes_ata_id", "atas_mudanca_revisoes")
    op.drop_table("atas_mudanca_revisoes")
    op.drop_index("ix_atas_mudanca_obra_id", "atas_mudanca")
    op.drop_table("atas_mudanca")
