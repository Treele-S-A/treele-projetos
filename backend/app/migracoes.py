"""Aplicação das migrações de esquema na inicialização.

Substitui o antigo `create_all`, que só criava tabelas faltantes e **nunca**
alterava as existentes. Enquanto o esquema não mudava isso passava despercebido;
a primeira coluna nova num banco com dados reais teria falhado em silêncio.
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect

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


def aplicar(engine: Engine) -> None:
    """Leva o banco até a última migração."""
    tabelas = set(inspect(engine).get_table_names())

    if tabelas and "alembic_version" not in tabelas:
        # Banco anterior ao Alembic: as tabelas existem mas não há histórico.
        # Sem carimbar, o Alembic tentaria criar tudo de novo e falharia.
        command.stamp(_config(), BASELINE)
        print("banco existente carimbado com a migração inicial", flush=True)

    command.upgrade(_config(), "head")
