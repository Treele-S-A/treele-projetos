"""Solicitação de revisão

A obra (ou o coordenador) pede alteração num projeto liberado, dizendo o que
deve mudar e, se quiser, anexando fotos ou PDFs marcados. Fecha quando a
revisão nova é liberada.

Revision ID: f4d6b8c0e2a3
Revises: e3c5a7b9d1f2
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4d6b8c0e2a3"
down_revision: Union[str, Sequence[str], None] = "e3c5a7b9d1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "solicitacoes_revisao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "documento_id", sa.Integer(),
            sa.ForeignKey("documentos.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "revisao_id", sa.Integer(),
            sa.ForeignKey("revisoes.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criada_por_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("atendida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "atendida_por_revisao_id", sa.Integer(),
            sa.ForeignKey("revisoes.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index(
        "ix_solicitacoes_revisao_documento_id", "solicitacoes_revisao", ["documento_id"]
    )
    op.create_index("ix_solicitacoes_revisao_status", "solicitacoes_revisao", ["status"])

    op.create_table(
        "anexos_solicitacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "solicitacao_id", sa.Integer(),
            sa.ForeignKey("solicitacoes_revisao.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("nome_original", sa.String(length=300), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("tamanho", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_anexos_solicitacao_solicitacao_id", "anexos_solicitacao", ["solicitacao_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_anexos_solicitacao_solicitacao_id", table_name="anexos_solicitacao")
    op.drop_table("anexos_solicitacao")
    op.drop_index("ix_solicitacoes_revisao_status", table_name="solicitacoes_revisao")
    op.drop_index("ix_solicitacoes_revisao_documento_id", table_name="solicitacoes_revisao")
    op.drop_table("solicitacoes_revisao")
