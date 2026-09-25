"""Aplicação das migrações de esquema na inicialização.

Substitui o antigo `create_all`, que só criava tabelas faltantes e **nunca**
alterava as existentes. Enquanto o esquema não mudava isso passava despercebido;
a primeira coluna nova num banco com dados reais teria falhado em silêncio.
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from .config import BASE_DIR, settings

# Primeira migração — a que descreve o esquema como ele era antes de o Alembic
# entrar. Bancos criados pelo `create_all` correspondem exatamente a ela.
BASELINE = "b7fc1b5ff4b9"


def _config() -> Config:
    # Config sem arquivo .ini de propósito: passar o ini faria o env.py chamar
    # fileConfig e reconfigurar o log da aplicação inteira.
    cfg = Config()
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def _conferir_schema(engine: Engine) -> None:
    """Confirma que as transações estão mesmo no schema isolado, antes de migrar.

    O schema é aplicado por um evento a cada transação (ver app/db.py). Se esse
    mecanismo deixar de funcionar — uma atualização de biblioteca, um ajuste
    mal feito —, as tabelas iriam parar no "public" de outra aplicação sem erro
    nenhum. Conferir aqui, na subida, transforma essa falha silenciosa numa
    falha com a causa escrita.
    """
    with engine.connect() as conn:
        atual = conn.execute(text("select current_schema()")).scalar()
    if atual != settings.db_schema:
        raise RuntimeError(
            f"DB_SCHEMA é '{settings.db_schema}', mas a transação está em "
            f"'{atual}'. O schema não está sendo aplicado — nada foi migrado, "
            "para não criar tabelas no lugar errado."
        )


def _criar_schema(engine: Engine) -> None:
    """Cria o schema isolado, uma vez, antes de qualquer outra conexão.

    Aqui na subida só existe uma conexão por vez, então o CREATE SCHEMA não
    disputa com ninguém. E precisa vir antes da conferência: enquanto o schema
    não existe, o Postgres o pula no search_path e responde "public".
    """
    with engine.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"')


def aplicar(engine: Engine) -> None:
    """Leva o banco até a última migração."""
    if settings.db_schema and engine.dialect.name == "postgresql":
        _criar_schema(engine)
        _conferir_schema(engine)

    tabelas = set(
        inspect(engine).get_table_names(schema=settings.db_schema or None)
    )

    with engine.connect() as conn:
        # A conexão vai junto para o env.py: é ela que diz qual banco migrar.
        # Sem isto o env.py migraria sempre o banco da aplicação, qualquer que
        # fosse a engine recebida aqui.
        cfg = _config()
        cfg.attributes["connection"] = conn

        if tabelas and "alembic_version" not in tabelas:
            # Banco anterior ao Alembic: as tabelas existem mas não há
            # histórico. Sem carimbar, o Alembic tentaria criar tudo de novo e
            # falharia.
            command.stamp(cfg, BASELINE)
            print("banco existente carimbado com a migração inicial", flush=True)

        command.upgrade(cfg, "head")
