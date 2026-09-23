"""Ambiente do Alembic.

A URL do banco vem da configuração da aplicação, não do alembic.ini — assim
migração e aplicação nunca apontam para bancos diferentes.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def executar_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def executar_online() -> None:
    # A mesma engine da aplicação, não uma criada aqui a partir do ini: assim
    # a migração herda os mesmos ajustes de conexão (schema isolado, prepared
    # statements desligados para o pooler) e não existe o risco de migrar num
    # schema e a aplicação ler de outro.
    with engine.connect() as conn:
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite não sabe ALTER COLUMN; o modo "batch" recria a tabela por
            # baixo dos panos. Sem isto, migração que altera coluna só rodaria
            # em Postgres.
            render_as_batch=settings.database_url.startswith("sqlite"),
            # O controle de versão do Alembic mora junto com as tabelas dele,
            # não no "public" de outra aplicação.
            version_table_schema=settings.db_schema or None,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    executar_offline()
else:
    executar_online()
