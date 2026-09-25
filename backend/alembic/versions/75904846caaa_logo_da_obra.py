"""Logo do empreendimento

Cada obra da treèle é um empreendimento com marca própria (Milos, Treviso,
Mykonos...). Guarda-se a chave no armazenamento e o tipo da imagem; o endereço
para exibir é assinado a cada leitura, porque expira.

Revision ID: 75904846caaa
Revises: 517cc7e6da89
Create Date: 2026-09-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "75904846caaa"
down_revision: Union[str, Sequence[str], None] = "517cc7e6da89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("obras", schema=None) as batch_op:
        batch_op.add_column(sa.Column("logo_chave", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("logo_tipo", sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("obras", schema=None) as batch_op:
        batch_op.drop_column("logo_tipo")
        batch_op.drop_column("logo_chave")
