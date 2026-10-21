"""Vistas do modelo 3D e projetistas marcados na solicitação

Uma vista guarda a cena do visualizador (modelos, câmera, cortes, seleção) e a
imagem com as marcações; a solicitação de revisão aponta para a vista de onde
saiu e para os projetistas que o coordenador marcou.

Revision ID: a1c3e5f7b9d2
Revises: d8f0a2c4e6b8
Create Date: 2026-10-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, Sequence[str], None] = "d8f0a2c4e6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vistas_modelo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("obra_id", sa.Integer(), sa.ForeignKey("obras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("arquivos", sa.JSON(), nullable=False),
        sa.Column("camera", sa.JSON(), nullable=False),
        sa.Column("cortes", sa.JSON(), nullable=False),
        sa.Column("selecao", sa.JSON(), nullable=False),
        sa.Column("ocultos", sa.JSON(), nullable=False),
        sa.Column("imagem_key", sa.String(500), nullable=False, unique=True),
        sa.Column("imagem_tamanho", sa.BigInteger(), nullable=False),
        sa.Column("criada_por_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vistas_modelo_obra_id", "vistas_modelo", ["obra_id"])
    op.create_table(
        "mencoes_solicitacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("solicitacao_id", sa.Integer(),
                  sa.ForeignKey("solicitacoes_revisao.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("solicitacao_id", "usuario_id", name="uq_mencao"),
    )
    op.create_index("ix_mencoes_solicitacao_solicitacao_id", "mencoes_solicitacao", ["solicitacao_id"])
    with op.batch_alter_table("solicitacoes_revisao") as t:
        t.add_column(sa.Column("vista_id", sa.Integer(), nullable=True))
        t.create_foreign_key(
            "fk_solicitacoes_vista", "vistas_modelo", ["vista_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("solicitacoes_revisao") as t:
        t.drop_constraint("fk_solicitacoes_vista", type_="foreignkey")
        t.drop_column("vista_id")
    op.drop_index("ix_mencoes_solicitacao_solicitacao_id", table_name="mencoes_solicitacao")
    op.drop_table("mencoes_solicitacao")
    op.drop_index("ix_vistas_modelo_obra_id", table_name="vistas_modelo")
    op.drop_table("vistas_modelo")
