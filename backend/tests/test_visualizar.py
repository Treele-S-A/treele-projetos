"""Visualizar PDF no navegador — a mesma leitura do download, sem baixar."""

from urllib.parse import urlsplit

import pytest

from .conftest import autenticar, autorizar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
DWG = b"AC1032" + b"\x00" * 200


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": "VIS", "nome": "Obra visualizar"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def _enviar(cliente, admin, obra, nome, conteudo, liberar):
    r = enviar_arquivo(cliente, admin, obra["id"], nome, conteudo)
    assert r.status_code == 200, r.text
    corpo = r.json()
    if liberar:
        p = cliente.post(f"/revisoes/{corpo['revisao']['id']}/publicar", json={}, headers=admin)
        assert p.status_code == 200, p.text
    return corpo["arquivo"]


@pytest.fixture(scope="module")
def da_obra(cliente, admin, obra):
    r = cliente.post(
        "/usuarios",
        json={"nome": "Campo", "email": "campo-vis@teste.com.br", "senha": "senha-campo-vis"},
        headers=admin,
    )
    cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": r.json()["id"], "papel": "obra"},
        headers=admin,
    )
    return autenticar(cliente, "campo-vis@teste.com.br", "senha-campo-vis")


def _abrir(cliente, url):
    partes = urlsplit(url)
    return cliente.get(f"{partes.path}?{partes.query}")


def test_pdf_abre_no_navegador_sem_baixar(cliente, admin, obra):
    arquivo = _enviar(cliente, admin, obra, "VIS-ARQ-PE-001-R00.pdf", PDF, liberar=True)

    r = cliente.get(f"/arquivos/{arquivo['id']}/visualizar", headers=admin)

    assert r.status_code == 200, r.text
    aberto = _abrir(cliente, r.json()["url"])
    assert aberto.status_code == 200
    assert aberto.headers["content-type"] == "application/pdf"
    assert aberto.headers["content-disposition"].startswith("inline")
    assert aberto.headers["x-content-type-options"] == "nosniff"
    assert aberto.content == PDF


def test_visualizacao_fica_no_registro(cliente, admin, obra):
    arquivo = _enviar(cliente, admin, obra, "VIS-ARQ-PE-002-R00.pdf", PDF, liberar=True)
    cliente.get(f"/arquivos/{arquivo['id']}/visualizar", headers=admin)

    evento = cliente.get(f"/obras/{obra['id']}/eventos", headers=admin).json()["itens"][0]
    assert evento["acao"] == "visualizacao"
    assert evento["detalhes"]["arquivo"] == "VIS-ARQ-PE-002-R00.pdf"


def test_so_pdf_abre_no_navegador(cliente, admin, obra):
    arquivo = _enviar(cliente, admin, obra, "VIS-ARQ-PE-003-R00.dwg", DWG, liberar=False)
    assert cliente.get(f"/arquivos/{arquivo['id']}/visualizar", headers=admin).status_code == 415


def test_link_de_download_nao_abre_como_pdf(cliente, admin, obra):
    """A ação vai na assinatura: trocar "get" por "pdf" no link invalida."""
    arquivo = _enviar(cliente, admin, obra, "VIS-ARQ-PE-004-R00.pdf", PDF, liberar=True)
    url = cliente.get(f"/arquivos/{arquivo['id']}/download", headers=admin).json()["url"]
    assert _abrir(cliente, url.replace("acao=get", "acao=pdf")).status_code == 403


def test_visualizar_segue_as_regras_do_download(cliente, admin, obra, da_obra):
    """Quem não pode baixar não pode abrir; e o obsoleto vem com aviso."""
    em_andamento = _enviar(cliente, admin, obra, "VIS-ARQ-PE-005-R00.pdf", PDF, liberar=False)
    assert (
        cliente.get(f"/arquivos/{em_andamento['id']}/visualizar", headers=da_obra).status_code
        == 403
    )

    antigo = _enviar(cliente, admin, obra, "VIS-ARQ-PE-006-R00.pdf", PDF, liberar=True)
    autorizar(cliente, admin, obra["id"], "VIS-ARQ-PE-006")
    _enviar(cliente, admin, obra, "VIS-ARQ-PE-006-R01.pdf", PDF, liberar=True)
    r = cliente.get(f"/arquivos/{antigo['id']}/visualizar", headers=da_obra)
    assert r.status_code == 200, r.text
    assert "OBSOLETA" in r.json()["aviso"]


def test_comercial_so_abre_o_que_pode_baixar(cliente, admin, obra):
    cliente.post(
        "/usuarios",
        json={
            "nome": "Comercial", "email": "comercial-vis@teste.com.br",
            "senha": "senha-comercial-vis", "comercial": True,
        },
        headers=admin,
    )
    comercial = autenticar(cliente, "comercial-vis@teste.com.br", "senha-comercial-vis")

    arq = _enviar(cliente, admin, obra, "VIS-ARQ-PE-007-R00.pdf", PDF, liberar=True)
    com = _enviar(cliente, admin, obra, "VIS-COM-PE-001-R00.pdf", PDF, liberar=True)

    assert cliente.get(f"/arquivos/{arq['id']}/visualizar", headers=comercial).status_code == 404
    assert cliente.get(f"/arquivos/{com['id']}/visualizar", headers=comercial).status_code == 200
