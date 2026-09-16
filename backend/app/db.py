"""Sessão de banco. Funciona igual em SQLite (dev) e Postgres (docker)."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

conecta_args = {}
if settings.database_url.startswith("sqlite"):
    conecta_args["check_same_thread"] = False

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


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
