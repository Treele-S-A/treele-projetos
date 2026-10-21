"""Avaliações do chat do acervo

👍 ou 👎 numa resposta, com a conversa avaliada, as etapas e um comentário
opcional — para saber onde o assistente erra.

Revision ID: d8f0a2c4e6b8
Revises: c7e9a1b3d5f7
Create Date: 2026-10-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8f0a2c4e6b8"
down_revision: Union[str, Sequence[str], None] = "c7e9a1b3d5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "avaliacoes_chat",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("obra_id", sa.Integer(),
                  sa.ForeignKey("obras.id", ondelete="SET NULL"), nullable=True),
        sa.Column("nota", sa.Integer(), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("conversa", sa.JSON(), nullable=False),
        sa.Column("etapas", sa.JSON(), nullable=False),
        sa.Column("fornecedor", sa.String(20), nullable=True),
        sa.Column("modelo", sa.String(80), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_avaliacoes_chat_nota", "avaliacoes_chat", ["nota"])


def downgrade() -> None:
    op.drop_index("ix_avaliacoes_chat_nota", table_name="avaliacoes_chat")
    op.drop_table("avaliacoes_chat")
