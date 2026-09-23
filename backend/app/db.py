"""Sessão de banco. Funciona igual em SQLite (dev) e Postgres (docker)."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

conecta_args = {}
if settings.database_url.startswith("sqlite"):
    conecta_args["check_same_thread"] = False
elif settings.database_url.startswith("postgresql"):
    # Hospedagens gerenciadas (Supabase, entre outras) atendem pelo *pooler*
    # em modo transaction: cada transação pode cair numa conexão física
    # diferente do Postgres. Prepared statement do lado do servidor pressupõe
    # a mesma conexão entre usos, então aqui ele quebraria de forma
    # intermitente. Desligar custa nada perceptível numa API deste tamanho.
    conecta_args["prepare_threshold"] = None

engine = create_engine(
    settings.database_url,
    connect_args=conecta_args,
    pool_pre_ping=True,
    future=True,
)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - infra
        cur = dbapi_conn.cursor()
        # Sem isto o SQLite ignora silenciosamente as chaves estrangeiras.
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

if settings.database_url.startswith("postgresql") and settings.db_schema:
    # Toda tabela sem prefixo (as de sempre, em app/models.py) é resolvida pelo
    # search_path. Apontá-lo para o schema próprio é o que mantém este sistema
    # sem tocar nas tabelas de outra aplicação que more no mesmo banco.
    #
    # O schema em si é criado uma única vez, na subida (app/migracoes.py) —
    # não aqui, a cada conexão: CREATE SCHEMA IF NOT EXISTS disparado por
    # várias conexões ao mesmo tempo corre em disputa, e uma delas falha.

    @event.listens_for(engine, "begin")
    def _schema_na_transacao(conn):  # pragma: no cover - infra
        # SET LOCAL, a cada transação — e não SET uma vez por conexão. O pooler
        # do Supabase em modo transaction entrega cada transação a uma conexão
        # física possivelmente diferente; configuração de sessão se perderia
        # no caminho, e as tabelas iriam parar no "public" de vez em quando,
        # sem erro nenhum. Valendo só para a transação, o schema vai junto com
        # ela, em qualquer modo de pooler. Custa um comando a mais por
        # transação — nada, nesta escala.
        conn.exec_driver_sql(f'SET LOCAL search_path TO "{settings.db_schema}", public')


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
