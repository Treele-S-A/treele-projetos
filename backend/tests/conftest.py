"""Ambiente de teste isolado.

As variáveis precisam ser definidas **antes** de importar `app`, porque a
configuração e o armazenamento são resolvidos na importação do módulo.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="treele-teste-"))

os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'teste.db').as_posix()}"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_LOCAL_DIR"] = str(_TMP / "storage")
os.environ["SECRET_KEY"] = "chave-de-teste"
os.environ["ADMIN_EMAIL"] = "admin@teste.com.br"
os.environ["ADMIN_SENHA"] = "senha-de-teste-1234"
os.environ["BASE_URL"] = "http://testserver"
# A ata de análise crítica antes de liberar tem os próprios testes
# (test_atas.py, que a ligam); nos outros, liberar continua sendo um passo só.
os.environ["ATA_ANALISE_OBRIGATORIA"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

SENHA_ADMIN = "senha-de-teste-1234"
EMAIL_ADMIN = "admin@teste.com.br"


@pytest.fixture(scope="session", autouse=True)
def _limpar_ao_fim():
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def cliente():
    with TestClient(app) as c:
        yield c


def autenticar(cliente, email: str, senha: str) -> dict:
    r = cliente.post("/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def admin(cliente):
    return autenticar(cliente, EMAIL_ADMIN, SENHA_ADMIN)


SEM_TITULO = object()
SEM_DESCRICAO = object()


def autorizar(cliente, coordenador, obra_id: int, codigo: str,
              motivo: str = "Revisão autorizada pelo escritório, para teste."):
    """Autoriza revisão nova do documento, como o coordenador faz na tela.

    Documento liberado só aceita revisão nova com revisão autorizada (TREELE,
    05/10/2026). O pedido do coordenador já nasce autorizado.
    """
    itens = cliente.get(
        f"/obras/{obra_id}/documentos?busca={codigo}", headers=coordenador
    ).json()["itens"]
    documento = next(d for d in itens if d["codigo"] == codigo)
    r = cliente.post(
        f"/documentos/{documento['id']}/solicitacoes", json={"descricao": motivo},
        headers=coordenador,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "autorizada", r.text
    return r.json()


def enviar_arquivo(cliente, cabecalhos, obra_id: int, nome: str, conteudo: bytes,
                   substituir: bool = False, titulo="Prancha de teste",
                   descricao="Emissão para teste", autorizar_com=None, avisar=None):
    """Executa os três passos do envio e devolve a resposta da confirmação.

    Manda um título e uma descrição por padrão, porque documento novo exige
    título e revisão nova exige "o que mudou". Passe ``titulo=SEM_TITULO`` ou
    ``descricao=SEM_DESCRICAO`` para testar justamente a falta deles.

    ``autorizar_com`` (cabeçalhos de um coordenador) autoriza antes a revisão
    nova de um documento já liberado — o código vem do nome, antes do "-R".

    ``avisar`` vai no corpo da confirmação; sem ele, a confirmação sai sem
    corpo, como nas telas antigas.
    """
    from urllib.parse import urlsplit

    if autorizar_com is not None:
        autorizar(cliente, autorizar_com, obra_id, nome.rsplit("-R", 1)[0])

    corpo = {"nome_arquivo": nome, "tamanho": len(conteudo), "substituir": substituir}
    if titulo is not SEM_TITULO:
        corpo["titulo"] = titulo
    if descricao is not SEM_DESCRICAO:
        corpo["descricao"] = descricao
    inicio = cliente.post(
        f"/obras/{obra_id}/uploads/iniciar", json=corpo, headers=cabecalhos
    )
    if inicio.status_code >= 400:
        return inicio

    dados = inicio.json()
    partes = urlsplit(dados["url"])
    caminho = f"{partes.path}?{partes.query}"

    envio = cliente.put(caminho, content=conteudo)
    assert envio.status_code == 200, envio.text

    return cliente.post(
        f"/arquivos/{dados['arquivo_id']}/confirmar", headers=cabecalhos,
        **({"json": {"avisar": avisar}} if avisar is not None else {}),
    )
