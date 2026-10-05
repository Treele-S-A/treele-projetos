"""Autorização de revisão

O coordenador autoriza ou recusa o pedido de revisão da obra; sem pedido
autorizado, o documento não aceita revisão nova. A notificação passa a
guardar a revisão de que trata.

Revision ID: b6f8d0e2a4c5
Revises: a5e7c9d1f3b4
Create Date: 2026-10-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6f8d0e2a4c5"
down_revision: Union[str, Sequence[str], None] = "a5e7c9d1f3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("solicitacoes_revisao") as t:
        t.add_column(sa.Column("decidida_em", sa.DateTime(timezone=True), nullable=True))
        t.add_column(sa.Column("decidida_por_id", sa.Integer(), nullable=True))
        t.add_column(sa.Column("motivo_recusa", sa.Text(), nullable=True))
        t.create_foreign_key(
            "fk_solicitacoes_revisao_decidida_por", "usuarios", ["decidida_por_id"], ["id"]
        )
    with op.batch_alter_table("notificacoes") as t:
        t.add_column(sa.Column("revisao_id", sa.Integer(), nullable=True))
        t.create_foreign_key(
            "fk_notificacoes_revisao", "revisoes", ["revisao_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("notificacoes") as t:
        t.drop_constraint("fk_notificacoes_revisao", type_="foreignkey")
        t.drop_column("revisao_id")
    with op.batch_alter_table("solicitacoes_revisao") as t:
        t.drop_constraint("fk_solicitacoes_revisao_decidida_por", type_="foreignkey")
        t.drop_column("motivo_recusa")
        t.drop_column("decidida_por_id")
        t.drop_column("decidida_em")
