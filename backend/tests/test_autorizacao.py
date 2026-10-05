"""Autorização de revisão (TREELE, 05/10/2026).

A obra pede, o coordenador autoriza ou recusa; o coordenador também autoriza
direto. Documento liberado só aceita revisão nova com revisão autorizada.
"""

from urllib.parse import urlsplit

import pytest

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
PEDIDO = "Deslocar o ralo do banheiro social 30 cm para a esquerda."
SENHA = "senha-aut-12345"


def _usuario(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@aut.teste.com.br"
    r = cliente.post(
        "/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA}, headers=admin
    )
    assert r.status_code == 201, r.text
    cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": r.json()["id"], "papel": papel},
        headers=admin,
    )
    return autenticar(cliente, email, SENHA)


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": "AUT", "nome": "Obra autorização"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def p(cliente, admin, obra):
    return {
        "campo": _usuario(cliente, admin, obra, "campo", "obra"),
        "proj": _usuario(cliente, admin, obra, "proj", "projetista"),
        "coord": _usuario(cliente, admin, obra, "coord", "coordenador"),
    }


def _liberado(cliente, admin, obra, prancha):
    r = enviar_arquivo(cliente, admin, obra["id"], f"AUT-ARQ-PE-{prancha}-R00.pdf", PDF)
    assert r.status_code == 200, r.text
    cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={}, headers=admin)
    return _doc(cliente, admin, obra, prancha)


def _doc(cliente, admin, obra, prancha):
    itens = cliente.get(
        f"/obras/{obra['id']}/documentos?busca=AUT-ARQ-PE-{prancha}", headers=admin
    ).json()["itens"]
    return itens[0]["id"]


def _r01(cliente, cab, obra, prancha):
    return enviar_arquivo(cliente, cab, obra["id"], f"AUT-ARQ-PE-{prancha}-R01.pdf", PDF)


def _pedir(cliente, cab, doc):
    r = cliente.post(f"/documentos/{doc}/solicitacoes", json={"descricao": PEDIDO}, headers=cab)
    assert r.status_code == 201, r.text
    return r.json()


def test_liberado_sem_autorizacao_nao_aceita_revisao_nova(cliente, admin, obra, p):
    _liberado(cliente, admin, obra, "001")
    r = _r01(cliente, p["proj"], obra, "001")
    assert r.status_code == 409
    assert "não tem revisão autorizada" in r.json()["detail"]["erros"][0]

    # A conferência do nome já avisa, antes de subir o arquivo.
    v = cliente.post(
        f"/obras/{obra['id']}/nomenclatura/validar",
        json={"nomes": ["AUT-ARQ-PE-001-R01.pdf", "AUT-ARQ-PE-001-R00.dwg"]},
        headers=p["proj"],
    ).json()["resultados"]
    assert v[0]["valido"] is False
    assert "não tem revisão autorizada" in v[0]["erros"][0]
    # Arquivo novo na revisão já liberada não é revisão nova: passa.
    assert v[1]["valido"] is True


def test_pedido_da_obra_sem_autorizacao_nao_libera_o_envio(cliente, admin, obra, p):
    _liberado(cliente, admin, obra, "002")
    pedido = _pedir(cliente, p["campo"], _doc(cliente, admin, obra, "002"))
    assert pedido["status"] == "aberta"
    assert _r01(cliente, p["proj"], obra, "002").status_code == 409

    autorizado = cliente.post(f"/solicitacoes/{pedido['id']}/autorizar", headers=p["coord"])
    assert autorizado.status_code == 200, autorizado.text
    r = _r01(cliente, p["proj"], obra, "002")
    assert r.status_code == 200, r.text


def test_pedido_recusado_nao_libera_o_envio(cliente, admin, obra, p):
    _liberado(cliente, admin, obra, "003")
    pedido = _pedir(cliente, p["campo"], _doc(cliente, admin, obra, "003"))
    r = cliente.post(
        f"/solicitacoes/{pedido['id']}/recusar",
        json={"motivo": "Segue o projeto aprovado na prefeitura."},
        headers=p["coord"],
    )
    assert r.status_code == 200, r.text
    assert _r01(cliente, p["proj"], obra, "003").status_code == 409


def test_coordenador_autoriza_direto_e_a_revisao_sobe(cliente, admin, obra, p):
    _liberado(cliente, admin, obra, "004")
    pedido = _pedir(cliente, p["coord"], _doc(cliente, admin, obra, "004"))
    assert pedido["status"] == "autorizada"
    assert pedido["decidida_em"] is not None
    assert _r01(cliente, p["proj"], obra, "004").status_code == 200


def test_so_o_coordenador_decide(cliente, admin, obra, p):
    _liberado(cliente, admin, obra, "005")
    pedido = _pedir(cliente, p["campo"], _doc(cliente, admin, obra, "005"))
    for quem in ("campo", "proj"):
        r = cliente.post(f"/solicitacoes/{pedido['id']}/autorizar", headers=p[quem])
        assert r.status_code == 403, quem


def test_documento_so_com_revisao_cancelada_aceita_a_proxima(cliente, admin, obra, p):
    r = enviar_arquivo(cliente, admin, obra["id"], "AUT-ARQ-PE-006-R00.pdf", PDF)
    c = cliente.post(
        f"/revisoes/{r.json()['revisao']['id']}/cancelar",
        json={"motivo": "Enviada na obra errada."},
        headers=admin,
    )
    assert c.status_code == 200, c.text
    assert _r01(cliente, p["proj"], obra, "006").status_code == 200


def test_liberacao_so_marca_pedido_autorizado(cliente, admin, obra, p):
    _liberado(cliente, admin, obra, "007")
    doc = _doc(cliente, admin, obra, "007")
    aberto = _pedir(cliente, p["campo"], doc)
    autorizado = _pedir(cliente, p["coord"], doc)
    r01 = _r01(cliente, p["proj"], obra, "007")
    revisao = r01.json()["revisao"]["id"]

    nao = cliente.post(
        f"/revisoes/{revisao}/publicar", json={"solicitacoes_atendidas": [aberto["id"]]},
        headers=admin,
    )
    assert nao.status_code == 422
    sim = cliente.post(
        f"/revisoes/{revisao}/publicar", json={"solicitacoes_atendidas": [autorizado["id"]]},
        headers=admin,
    )
    assert sim.status_code == 200, sim.text
    detalhe = cliente.get(f"/documentos/{doc}", headers=admin).json()
    estados = {s["id"]: s["status"] for s in detalhe["solicitacoes"]}
    assert estados == {aberto["id"]: "aberta", autorizado["id"]: "atendida"}
    assert detalhe["solicitacoes_abertas"] == 1
    assert detalhe["solicitacoes_autorizadas"] == 0


def test_marcas_na_lista(cliente, admin, obra, p):
    _liberado(cliente, admin, obra, "008")
    doc = _doc(cliente, admin, obra, "008")
    _pedir(cliente, p["campo"], doc)
    _pedir(cliente, p["coord"], doc)
    item = next(
        d for d in cliente.get(f"/obras/{obra['id']}/documentos", headers=p["campo"]).json()["itens"]
        if d["id"] == doc
    )
    assert item["solicitacoes_abertas"] == 1
    assert item["solicitacoes_autorizadas"] == 1


def test_pedido_do_coordenador_aceita_anexo(cliente, admin, obra, p):
    """Nasce autorizado, e o anexo vem logo depois de criado."""
    _liberado(cliente, admin, obra, "009")
    pedido = _pedir(cliente, p["coord"], _doc(cliente, admin, obra, "009"))
    r = cliente.post(
        f"/solicitacoes/{pedido['id']}/anexos",
        json={"nome_arquivo": "croqui.png", "tamanho": len(PNG)},
        headers=p["coord"],
    )
    assert r.status_code == 201, r.text
    partes = urlsplit(r.json()["url"])
    assert cliente.put(f"{partes.path}?{partes.query}", content=PNG).status_code == 200
    ok = cliente.post(f"/anexos/{r.json()['anexo_id']}/confirmar", headers=p["coord"])
    assert ok.status_code == 200, ok.text
