"""Preparação do banco na inicialização: migrar o esquema e completar os catálogos.

Substitui o antigo `create_all`, que só criava tabelas faltantes e **nunca**
alterava as existentes. Enquanto o esquema não mudava isso passava despercebido;
a primeira coluna nova num banco com dados reais teria falhado em silêncio.

Várias instâncias podem subir ao mesmo tempo — na Vercel, cada pico de acesso
liga instâncias novas; no Render, basta ter duas. Sem coordenação, duas delas
migrariam e semeariam juntas: a mesma coluna criada duas vezes, a mesma
disciplina inserida duas vezes. No Postgres, então, tudo acontece numa
transação só, sob uma trava do próprio banco: a primeira instância prepara,
as outras esperam e encontram o trabalho feito.
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import BASE_DIR, settings
from .seed import semear

# Primeira migração — a que descreve o esquema como ele era antes de o Alembic
# entrar. Bancos criados pelo `create_all` correspondem exatamente a ela.
BASELINE = "b7fc1b5ff4b9"

# Número da trava de inicialização. Qualquer inteiro de 64 bits serve; o que
# importa é ser sempre o mesmo e não colidir com trava de outra aplicação no
# mesmo banco — daí "treele" em hexadecimal, em vez de 1.
TRAVA_INICIALIZACAO = 0x747265656C65


def _config() -> Config:
    # Config sem arquivo .ini de propósito: passar o ini faria o env.py chamar
    # fileConfig e reconfigurar o log da aplicação inteira.
    cfg = Config()
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def _conferir_schema(conn: Connection) -> None:
    """Confirma que a transação está mesmo no schema isolado, antes de migrar.

    O schema é aplicado por um evento a cada transação (ver app/db.py). Se esse
    mecanismo deixar de funcionar — uma atualização de biblioteca, um ajuste
    mal feito —, as tabelas iriam parar no "public" de outra aplicação sem erro
    nenhum. Conferir aqui, na subida, transforma essa falha silenciosa numa
    falha com a causa escrita.
    """
    atual = conn.execute(text("select current_schema()")).scalar()
    if atual != settings.db_schema:
        raise RuntimeError(
            f"DB_SCHEMA é '{settings.db_schema}', mas a transação está em "
            f"'{atual}'. O schema não está sendo aplicado — nada foi migrado, "
            "para não criar tabelas no lugar errado."
        )


def _garantir_schema(engine: Engine) -> None:
    """Cria o schema isolado, numa transação só dele, ANTES da transação travada.

    Não pode ser dentro dela. Quem espera a trava já resolveu o search_path ao
    pedir a trava — e, se o schema ainda não existia, o Postgres guarda em
    cache que ele não existe. Quando a trava é liberada, essa instância tenta
    criar o schema de novo (e cai) ou, pior, segue com o search_path antigo e
    cria as tabelas no "public" de outra aplicação. Com o schema criado antes,
    toda transação travada já nasce enxergando ele.

    Seis instâncias subindo juntas pelo pooler reproduziram exatamente isso:
    cinco caíram no CREATE SCHEMA, dentro da trava.
    """
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"')
    except IntegrityError:
        # Outra instância criou no mesmo instante — o IF NOT EXISTS não é
        # atômico entre sessões. O schema existe, que era o objetivo.
        pass


def _migrar(conn: Connection) -> None:
    """Leva o banco da conexão até a última migração."""
    if settings.db_schema and conn.dialect.name == "postgresql":
        _conferir_schema(conn)

    # Schema isolado é coisa de Postgres. No SQLite, "schema" quer dizer outro
    # arquivo de banco anexado — passar o nome ali quebraria a subida.
    schema = settings.db_schema if conn.dialect.name == "postgresql" else ""
    tabelas = set(inspect(conn).get_table_names(schema=schema or None))

    # A conexão vai junto para o env.py: é ela que diz qual banco migrar — e,
    # no Postgres, dentro de qual transação.
    cfg = _config()
    cfg.attributes["connection"] = conn

    if tabelas and "alembic_version" not in tabelas:
        # Banco anterior ao Alembic: as tabelas existem mas não há histórico.
        # Sem carimbar, o Alembic tentaria criar tudo de novo e falharia.
        command.stamp(cfg, BASELINE)
        print("banco existente carimbado com a migração inicial", flush=True)

    command.upgrade(cfg, "head")


def preparar_banco(engine: Engine) -> None:
    """Migra o esquema e completa os catálogos, uma instância por vez."""
    if engine.dialect.name == "postgresql":
        if settings.db_schema:
            _garantir_schema(engine)

        # Trava de TRANSAÇÃO (xact), não de sessão: pelo pooler do Supabase em
        # modo transaction, cada transação pode cair numa conexão física
        # diferente, e uma trava de sessão ficaria presa numa conexão que esta
        # instância nem usa mais. A de transação vale enquanto a transação
        # durar e é liberada sozinha no commit — ou no rollback, se algo falhar.
        with engine.connect() as conn, conn.begin():
            conn.execute(
                text("select pg_advisory_xact_lock(:trava)"),
                {"trava": TRAVA_INICIALIZACAO},
            )
            # O Postgres faz DDL dentro de transação: se a migração falhar no
            # meio, nada fica pela metade. O Alembic percebe a transação
            # aberta e trabalha dentro dela, sem abrir outra.
            _migrar(conn)
            # A semente usa a mesma conexão (e a mesma trava). O commit dela
            # vira um savepoint; o commit de verdade é o da transação de fora.
            with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
                semear(db)
        return

    # SQLite: um processo só (desenvolvimento e testes), nada a coordenar. E a
    # migração precisa controlar as próprias transações aqui — o PRAGMA de
    # chave estrangeira do modo batch só vale fora de transação (alembic/env.py).
    with engine.connect() as conn:
        _migrar(conn)
    with Session(bind=engine) as db:
        semear(db)
