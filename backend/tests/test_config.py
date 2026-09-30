"""Testes da configuração — as duas regras que só aparecem ao subir em produção.

Nenhuma das duas tem tela: falham na inicialização, longe de quem usa. Por isso
merecem teste — é aqui que a gente descobre se continuam funcionando.
"""

import pytest

from app.config import SECRET_KEY_DEV, Settings, _conferir_producao


def _settings(**valores) -> Settings:
    # _env_file=None isola do backend/.env da máquina de quem roda o teste.
    base = {
        "ambiente": "producao",
        "secret_key": "x" * 48,
        "database_url": "postgresql://u:p@host:6543/postgres",
    }
    return Settings(_env_file=None, **{**base, **valores})


# --------------------------------------------------------------- SECRET_KEY


def test_producao_recusa_a_chave_de_desenvolvimento():
    with pytest.raises(RuntimeError, match="SECRET_KEY não chegou"):
        _conferir_producao(_settings(secret_key=SECRET_KEY_DEV))


def test_producao_recusa_chave_curta():
    with pytest.raises(RuntimeError, match="tem 31 caractere"):
        _conferir_producao(_settings(secret_key="x" * 31))


def test_producao_aceita_chave_propria_e_longa():
    _conferir_producao(_settings(secret_key="x" * 32))


def test_desenvolvimento_nao_exige_chave():
    """Exigir chave forte em dev só faria todo mundo colar a mesma em todo lugar."""
    _conferir_producao(_settings(ambiente="dev", secret_key=SECRET_KEY_DEV))


def test_erro_da_chave_nao_vaza_o_resto_da_configuracao():
    """O motivo de a conferência não ser um validador do pydantic.

    O ValidationError do pydantic imprime o modelo inteiro no texto do erro —
    e o modelo tem ADMIN_SENHA. Esse texto vai parar no log da hospedagem.
    """
    with pytest.raises(RuntimeError) as erro:
        _conferir_producao(
            _settings(secret_key="curta", admin_senha="senha-do-administrador")
        )
    assert "senha-do-administrador" not in str(erro.value)


@pytest.mark.parametrize(
    "colada, motivo",
    [
        ("SECRET_KEY = " + "x" * 48, "nome junto"),
        (" " + "x" * 48, "espaço ou aspas"),
        ('"' + "x" * 48 + '"', "espaço ou aspas"),
    ],
)
def test_chave_mal_colada_diz_o_que_houve(colada, motivo):
    """Os jeitos comuns de colar errado no painel. Todos passariam do tamanho
    mínimo — e a chave certa seria outra — então cada um tem aviso próprio."""
    with pytest.raises(RuntimeError, match=motivo) as erro:
        _conferir_producao(_settings(secret_key=colada))
    assert "x" * 48 not in str(erro.value)


# ------------------------------------------------ o resto da produção


def test_producao_sem_banco_e_recusada():
    """Sem DATABASE_URL o sistema cairia no SQLite padrão: banco vazio, e na
    Vercel nem abre (disco só leitura) — com um erro que não diz a causa."""
    padrao = Settings.model_fields["database_url"].default
    with pytest.raises(RuntimeError, match="DATABASE_URL não definida"):
        _conferir_producao(_settings(database_url=padrao))


def test_sqlite_escolhido_de_proposito_continua_valendo():
    _conferir_producao(_settings(database_url="sqlite:////srv/treele/treele.db"))


def test_senha_do_banco_esquecida_no_modelo():
    url = "postgresql://postgres.abc:[YOUR-PASSWORD]@host:6543/postgres"
    with pytest.raises(RuntimeError, match=r"\[YOUR-PASSWORD\]"):
        _conferir_producao(_settings(database_url=url))


def test_storage_s3_sem_chaves_e_recusado():
    with pytest.raises(RuntimeError) as erro:
        _conferir_producao(
            _settings(storage_backend="s3", s3_endpoint="https://s3.exemplo")
        )
    assert "S3_ACCESS_KEY" in str(erro.value)
    assert "S3_SECRET_KEY" in str(erro.value)
    assert "S3_ENDPOINT" not in str(erro.value)


def test_todos_os_problemas_numa_mensagem_so():
    """Na hospedagem, cada rodada de corrigir-publicar-ler o log custa minutos.
    Descobrir as variáveis que faltam uma por vez multiplica isso."""
    padrao = Settings.model_fields["database_url"].default
    with pytest.raises(RuntimeError) as erro:
        _conferir_producao(
            _settings(
                secret_key=SECRET_KEY_DEV,
                database_url=padrao,
                storage_backend="s3",
                s3_secret_key="segredo-do-storage",
            )
        )
    texto = str(erro.value)
    for esperado in ("SECRET_KEY", "DATABASE_URL", "S3_ENDPOINT", "S3_ACCESS_KEY"):
        assert esperado in texto
    assert "segredo-do-storage" not in texto


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
