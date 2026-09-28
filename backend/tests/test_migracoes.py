"""Migração sobre banco que já tem dados.

O resto da suíte sobe um banco vazio, e banco vazio aceita qualquer migração.
O que quebra na vida real é migrar o banco de alguém que já usa o sistema —
foi assim que apareceu a falha que este arquivo cobre.
"""

from alembic import command
from sqlalchemy import create_engine, event, inspect, text

from app.migracoes import BASELINE, _config


def _engine_como_a_aplicacao(caminho):
    """SQLite com chave estrangeira ligada, do mesmo jeito que app/db.py liga."""
    engine = create_engine(f"sqlite:///{caminho.as_posix()}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def _migrar(conn, alvo: str) -> None:
    cfg = _config()
    cfg.attributes["connection"] = conn
    command.upgrade(cfg, alvo)


def test_sqlite_com_dados_migra_ate_o_fim(tmp_path):
    """No SQLite, alterar coluna recria a tabela: cria a nova, copia e APAGA a
    antiga. Com chave estrangeira ligada, apagar "obras" apaga cada obra — e os
    documentos, revisões e arquivos vão junto em cascata, sem erro nenhum. Este
    teste pegou exatamente isso: sem a correção, a migração terminava "com
    sucesso" e a tabela de documentos saía vazia. O banco vazio do resto da
    suíte nunca mostraria.
    """
    engine = _engine_como_a_aplicacao(tmp_path / "em-uso.db")

    with engine.connect() as conn:
        _migrar(conn, BASELINE)
        conn.execute(text(
            "insert into disciplinas (id, codigo, nome, ordem, ativa) "
            "values (1, 'ARQ', 'Arquitetura', 1, 1)"
        ))
        conn.execute(text(
            "insert into fases (id, codigo, nome, ordem, ativa) "
            "values (1, 'PE', 'Projeto Executivo', 1, 1)"
        ))
        conn.execute(text(
            "insert into obras (id, codigo, nome, ativa, regra_companheiro, criado_em) "
            "values (1, 'MIL', 'Milos', 1, '{}', '2026-09-01 00:00:00')"
        ))
        conn.execute(text(
            "insert into documentos (id, obra_id, disciplina_id, fase_id, codigo, criado_em) "
            "values (1, 1, 1, 1, 'MIL-ARQ-PE-001', '2026-09-01 00:00:00')"
        ))
        conn.commit()

        _migrar(conn, "head")

        assert conn.execute(text("select nome from obras")).scalar() == "Milos"
        assert conn.execute(text("select obra_id from documentos")).scalar() == 1
        # A chave estrangeira precisa voltar ligada depois da migração —
        # desligá-la para migrar não pode vazar para o uso normal.
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1

    colunas = {c["name"] for c in inspect(engine).get_columns("obras")}
    assert "responsavel_id" in colunas
    assert not any(
        t.startswith("_alembic_tmp") for t in inspect(engine).get_table_names()
    )


def test_schema_isolado_e_ignorado_no_sqlite(tmp_path, monkeypatch):
    """DB_SCHEMA é coisa de Postgres. A entrada da Vercel liga ele por padrão,
    e rodá-la com SQLite (teste local) derrubava a subida: no SQLite, "schema"
    é outro arquivo de banco anexado, e "treele.sqlite_master" não existe."""
    from app.config import settings
    from app.migracoes import preparar_banco

    monkeypatch.setattr(settings, "db_schema", "treele")
    engine = _engine_como_a_aplicacao(tmp_path / "com-schema.db")

    preparar_banco(engine)

    assert "alembic_version" in inspect(engine).get_table_names()
    assert "disciplinas" in inspect(engine).get_table_names()
