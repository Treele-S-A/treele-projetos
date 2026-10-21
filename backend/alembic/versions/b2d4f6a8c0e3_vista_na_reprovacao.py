"""Vista do modelo 3D na reprovação da revisão

A reprovação na análise crítica pode levar a vista marcada do modelo 3D que
mostra o problema, além da observação.

Revision ID: b2d4f6a8c0e3
Revises: a1c3e5f7b9d2
Create Date: 2026-10-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f6a8c0e3"
down_revision: Union[str, Sequence[str], None] = "a1c3e5f7b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("revisoes") as t:
        t.add_column(sa.Column("vista_reprovacao_id", sa.Integer(), nullable=True))
        t.create_foreign_key(
            "fk_revisoes_vista_reprovacao", "vistas_modelo", ["vista_reprovacao_id"], ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("revisoes") as t:
        t.drop_constraint("fk_revisoes_vista_reprovacao", type_="foreignkey")
        t.drop_column("vista_reprovacao_id")
