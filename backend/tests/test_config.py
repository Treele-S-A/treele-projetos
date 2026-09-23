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
