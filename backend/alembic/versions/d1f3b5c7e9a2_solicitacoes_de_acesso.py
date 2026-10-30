"""Solicitações de acesso de quem é de fora da Treèle

Pedido de acesso (projetista ou comercial externo), disciplinas por membro da
obra (o projetista só vê as dele) e aviso sem obra (o pedido de acesso).

Revision ID: d1f3b5c7e9a2
Revises: c9e1a3b5d7f0
Create Date: 2026-10-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1f3b5c7e9a2"
down_revision: Union[str, Sequence[str], None] = "c9e1a3b5d7f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "solicitacoes_acesso",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(160), nullable=False),
        sa.Column("email", sa.String(190), nullable=False),
        sa.Column("empresa", sa.String(160), nullable=True),
        sa.Column("funcao", sa.String(20), nullable=False),
        sa.Column("obras", sa.JSON(), nullable=False),
        sa.Column("disciplinas", sa.JSON(), nullable=False),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decidida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decidida_por_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_solicitacoes_acesso_email", "solicitacoes_acesso", ["email"])
    op.create_index("ix_solicitacoes_acesso_status", "solicitacoes_acesso", ["status"])
    with op.batch_alter_table("obra_membros") as tabela:
        tabela.add_column(sa.Column("disciplinas", sa.JSON(), nullable=True))
    with op.batch_alter_table("notificacoes") as tabela:
        tabela.alter_column("obra_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("notificacoes") as tabela:
        tabela.alter_column("obra_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("obra_membros") as tabela:
        tabela.drop_column("disciplinas")
    op.drop_index("ix_solicitacoes_acesso_status", table_name="solicitacoes_acesso")
    op.drop_index("ix_solicitacoes_acesso_email", table_name="solicitacoes_acesso")
    op.drop_table("solicitacoes_acesso")
