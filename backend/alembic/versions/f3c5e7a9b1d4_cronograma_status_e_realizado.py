"""Cronograma: status no lugar do %, datas realizadas e plano congelado

O % concluído vira status (0 → não iniciado, 100 → concluído, o resto → em
andamento). Início e término realizados, e o início e término planejados
congelados quando a atividade começa — o histórico de atraso.

Revision ID: f3c5e7a9b1d4
Revises: e2b4d6f8a0c3
Create Date: 2026-11-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3c5e7a9b1d4"
down_revision: Union[str, Sequence[str], None] = "e2b4d6f8a0c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("cronograma_atividades") as tabela:
        tabela.add_column(sa.Column("status", sa.String(14), nullable=False, server_default="nao_iniciado"))
        tabela.add_column(sa.Column("inicio_real", sa.Date(), nullable=True))
        tabela.add_column(sa.Column("termino_real", sa.Date(), nullable=True))
        tabela.add_column(sa.Column("inicio_base", sa.Date(), nullable=True))
        tabela.add_column(sa.Column("termino_base", sa.Date(), nullable=True))
    op.execute(
        "UPDATE cronograma_atividades SET status = CASE "
        "WHEN progresso >= 100 THEN 'concluido' WHEN progresso > 0 THEN 'em_andamento' "
        "ELSE 'nao_iniciado' END"
    )
    with op.batch_alter_table("cronograma_atividades") as tabela:
        tabela.drop_column("progresso")


def downgrade() -> None:
    with op.batch_alter_table("cronograma_atividades") as tabela:
        tabela.add_column(sa.Column("progresso", sa.Integer(), nullable=False, server_default="0"))
    op.execute(
        "UPDATE cronograma_atividades SET progresso = CASE "
        "WHEN status = 'concluido' THEN 100 WHEN status = 'em_andamento' THEN 50 ELSE 0 END"
    )
    with op.batch_alter_table("cronograma_atividades") as tabela:
        tabela.drop_column("termino_base")
        tabela.drop_column("inicio_base")
        tabela.drop_column("termino_real")
        tabela.drop_column("inicio_real")
        tabela.drop_column("status")
