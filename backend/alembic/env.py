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


def _migrar(conn) -> None:
    sqlite = conn.dialect.name == "sqlite"

    if sqlite:
        # No SQLite, alterar coluna recria a tabela (modo "batch"): cria a
        # nova, copia os dados, APAGA a antiga e renomeia. Com a checagem de
        # chave estrangeira ligada (a aplicação liga, em app/db.py), apagar a
        # tabela "obras" equivale a apagar cada obra — e documentos, revisões
        # e arquivos vão junto, em cascata, sem erro nenhum. Só não acontece
        # quando algum evento de auditoria aponta para a obra (esse vínculo
        # não tem cascata e trava tudo). Desliga só durante a migração; o
        # PRAGMA não tem efeito dentro de transação, por isso o commit antes.
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.commit()

    try:
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite não sabe ALTER COLUMN; o modo "batch" recria a tabela por
            # baixo dos panos. Sem isto, migração que altera coluna só rodaria
            # em Postgres.
            render_as_batch=sqlite,
            # O controle de versão do Alembic mora junto com as tabelas dele,
            # não no "public" de outra aplicação. Só no Postgres: no SQLite,
            # "schema" seria outro arquivo de banco anexado.
            version_table_schema=(
                (settings.db_schema or None) if conn.dialect.name == "postgresql" else None
            ),
        )
        with context.begin_transaction():
            context.run_migrations()

        if sqlite:
            # Com a checagem desligada, nada impediu uma referência quebrada
            # durante a cópia. Confere agora, antes de religar.
            quebradas = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if quebradas:
                raise RuntimeError(
                    f"A migração deixou {len(quebradas)} referência(s) quebrada(s): "
                    f"{quebradas[:5]}"
                )
    finally:
        if sqlite:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            conn.commit()


def executar_online() -> None:
    # Quem chama pela aplicação (app/migracoes.py) entrega a conexão pronta —
    # é ela que decide qual banco migrar. Sem conexão entregue (a linha de
    # comando, `alembic revision --autogenerate`), usa a engine da aplicação,
    # não uma criada aqui a partir do ini: assim a migração herda os mesmos
    # ajustes de conexão (schema isolado, prepared statements desligados para
    # o pooler) e não existe o risco de migrar num schema e ler de outro.
    conn = config.attributes.get("connection")
    if conn is not None:
        _migrar(conn)
        return
    with engine.connect() as conn:
        _migrar(conn)


if context.is_offline_mode():
    executar_offline()
else:
    executar_online()
