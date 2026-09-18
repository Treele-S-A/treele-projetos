"""Engenheiro responsável pela obra

É para o responsável que as notificações vão, e é quem responde pela obra
perante a equipe. Papel diferente de "coordenador", que é permissão: pode
haver vários coordenadores, mas responsável é um só.

Revision ID: 517cc7e6da89
Revises: b7fc1b5ff4b9
Create Date: 2026-09-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "517cc7e6da89"
down_revision: Union[str, Sequence[str], None] = "b7fc1b5ff4b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A chave estrangeira é nomeada explicitamente: sem nome, o SQLite não
# consegue removê-la no downgrade e a migração fica sem volta.
FK = "fk_obras_responsavel_usuarios"


def upgrade() -> None:
    with op.batch_alter_table("obras", schema=None) as batch_op:
        batch_op.add_column(sa.Column("responsavel_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(FK, "usuarios", ["responsavel_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("obras", schema=None) as batch_op:
        batch_op.drop_constraint(FK, type_="foreignkey")
        batch_op.drop_column("responsavel_id")
