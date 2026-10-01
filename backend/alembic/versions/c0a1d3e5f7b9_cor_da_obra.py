"""Cor de identidade da obra

Cada empreendimento tem identidade visual própria; a cor dela pinta o cartão
e o cabeçalho da obra, como nos painéis da treèle. Guarda-se só a cor base
(#rrggbb) — o degradê é derivado dela na tela.

Revision ID: c0a1d3e5f7b9
Revises: 75904846caaa
Create Date: 2026-10-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c0a1d3e5f7b9"
down_revision: Union[str, Sequence[str], None] = "75904846caaa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("obras", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cor", sa.String(length=7), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("obras", schema=None) as batch_op:
        batch_op.drop_column("cor")
