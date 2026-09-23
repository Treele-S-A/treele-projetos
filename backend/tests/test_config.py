"""Testes da configuração — as duas regras que só aparecem ao subir em produção.

Nenhuma das duas tem tela: falham na inicialização, longe de quem usa. Por isso
merecem teste — é aqui que a gente descobre se continuam funcionando.
"""

import pytest

from app.config import SECRET_KEY_DEV, Settings, _conferir_chave


def _settings(**valores) -> Settings:
    # _env_file=None isola do backend/.env da máquina de quem roda o teste.
    base = {"ambiente": "producao", "secret_key": "x" * 48}
    return Settings(_env_file=None, **{**base, **valores})


# --------------------------------------------------------------- SECRET_KEY


def test_producao_recusa_a_chave_de_desenvolvimento():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _conferir_chave(_settings(secret_key=SECRET_KEY_DEV))


def test_producao_recusa_chave_curta():
    with pytest.raises(RuntimeError, match="32 caracteres"):
        _conferir_chave(_settings(secret_key="x" * 31))


def test_producao_aceita_chave_propria_e_longa():
    _conferir_chave(_settings(secret_key="x" * 32))


def test_desenvolvimento_nao_exige_chave():
    """Exigir chave forte em dev só faria todo mundo colar a mesma em todo lugar."""
    _conferir_chave(_settings(ambiente="dev", secret_key=SECRET_KEY_DEV))


def test_erro_da_chave_nao_vaza_o_resto_da_configuracao():
    """O motivo de a conferência não ser um validador do pydantic.

    O ValidationError do pydantic imprime o modelo inteiro no texto do erro —
    e o modelo tem ADMIN_SENHA. Esse texto vai parar no log da hospedagem.
    """
    with pytest.raises(RuntimeError) as erro:
        _conferir_chave(
            _settings(secret_key="curta", admin_senha="senha-do-administrador")
        )
    assert "senha-do-administrador" not in str(erro.value)


# ------------------------------------------------------------- DATABASE_URL


@pytest.mark.parametrize(
    "entrada",
    ["postgres://u:p@host:5432/treele", "postgresql://u:p@host:5432/treele"],
)
def test_url_do_banco_ganha_driver_explicito(entrada):
    """Render e afins entregam `postgres://`, que levaria o SQLAlchemy ao psycopg2."""
    assert (
        _settings(database_url=entrada).database_url
        == "postgresql+psycopg://u:p@host:5432/treele"
    )


def test_url_do_banco_ja_explicita_nao_muda():
    url = "postgresql+psycopg://u:p@host:5432/treele"
    assert _settings(database_url=url).database_url == url


def test_sqlite_nao_e_tocado():
    assert _settings(database_url="sqlite:///./treele.db").database_url.startswith(
        "sqlite:///"
    )


# ---------------------------------------------------------------- DB_SCHEMA


def test_schema_vazio_mantem_o_padrao_do_banco():
    """Vazio é o padrão, e precisa continuar sendo.

    Quem já roda em Postgres dedicado tem os dados em "public". Um padrão
    diferente faria o sistema achar o banco vazio na próxima subida.
    """
    assert _settings().db_schema == ""


def test_schema_valido_e_aceito():
    assert _settings(db_schema="treele").db_schema == "treele"


@pytest.mark.parametrize(
    "invalido",
    ['treele"; drop table usuarios; --', "Treele", "treele-projetos", "1treele"],
)
def test_schema_que_viraria_sql_solto_e_recusado(invalido):
    with pytest.raises(ValueError, match="DB_SCHEMA"):
        _settings(db_schema=invalido)


# ----------------------------------------------------------- ESTATICOS_DIR


@pytest.mark.parametrize("vazio", ["", "   "])
def test_estaticos_vazio_quer_dizer_sem_interface(vazio):
    """Sem isto, Path("") vira "." — e a subida cai procurando ./assets."""
    assert _settings(estaticos_dir=vazio).estaticos_dir is None
