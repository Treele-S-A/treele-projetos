"""Papel "cliente" deixa de existir

A TREELE não usa esse papel (02/10/2026). Nenhuma equipe o tinha; esta
migração existe só para que um registro perdido não derrube a leitura do
banco. Vira "obra", o papel mais próximo.

Revision ID: e3c5a7b9d1f2
Revises: d2b4f6a8c0e1
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e3c5a7b9d1f2"
down_revision: Union[str, Sequence[str], None] = "d2b4f6a8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE obra_membros SET papel = 'obra' WHERE papel = 'cliente'")


def downgrade() -> None:
    # Não há como saber quem era cliente antes: nada a desfazer.
    pass
