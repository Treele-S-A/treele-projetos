"""Fornecedores de projetos (PRO-FL-002)

Cadastro, qualificação documental e avaliação de desempenho dos projetistas.

Revision ID: b8d0f2a4c6e9
Revises: a7c9e1b3d5f8
Create Date: 2026-10-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d0f2a4c6e9"
down_revision: Union[str, Sequence[str], None] = "a7c9e1b3d5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fornecedores_projeto",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cod_sienge", sa.String(20), nullable=True),
        sa.Column("razao_social", sa.String(200), nullable=False),
        sa.Column("nome_fantasia", sa.String(200), nullable=True),
        sa.Column("cnpj", sa.String(20), nullable=True),
        sa.Column("contato", sa.String(120), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("telefone", sa.String(40), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("registro_conselho", sa.String(3), nullable=True),
        sa.Column("portfolio", sa.Boolean(), nullable=True),
        sa.Column("escopos", sa.JSON(), nullable=False),
        sa.Column("padroes", sa.JSON(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "avaliacoes_fornecedor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fornecedor_id", sa.Integer(),
                  sa.ForeignKey("fornecedores_projeto.id", ondelete="CASCADE"), nullable=False),
        sa.Column("obra_id", sa.Integer(), sa.ForeignKey("obras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("empreendimento", sa.String(200), nullable=False),
        sa.Column("escopo", sa.String(20), nullable=True),
        sa.Column("data", sa.DateTime(timezone=True), nullable=False),
        sa.Column("qualidade", sa.Integer(), nullable=False),
        sa.Column("documentacao", sa.Integer(), nullable=False),
        sa.Column("prazo", sa.Integer(), nullable=False),
        sa.Column("atendimento", sa.Integer(), nullable=False),
        sa.Column("media", sa.Float(), nullable=False),
        sa.Column("continua_qualificado", sa.Boolean(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("avaliado_por_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_avaliacoes_fornecedor_fornecedor_id", "avaliacoes_fornecedor", ["fornecedor_id"])


def downgrade() -> None:
    op.drop_index("ix_avaliacoes_fornecedor_fornecedor_id", table_name="avaliacoes_fornecedor")
    op.drop_table("avaliacoes_fornecedor")
    op.drop_table("fornecedores_projeto")
