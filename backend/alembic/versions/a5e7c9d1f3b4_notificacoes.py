"""Notificações

Aviso no sistema (e por e-mail) para pedido de revisão novo e revisão
liberada para obra.

Revision ID: a5e7c9d1f3b4
Revises: f4d6b8c0e2a3
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a5e7c9d1f3b4"
down_revision: Union[str, Sequence[str], None] = "f4d6b8c0e2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notificacoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "usuario_id", sa.Integer(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column(
            "obra_id", sa.Integer(),
            sa.ForeignKey("obras.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "documento_id", sa.Integer(),
            sa.ForeignKey("documentos.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("titulo", sa.String(length=300), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_enviado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notificacoes_usuario_lida", "notificacoes", ["usuario_id", "lida_em"]
    )


def downgrade() -> None:
    op.drop_index("ix_notificacoes_usuario_lida", table_name="notificacoes")
    op.drop_table("notificacoes")
