"""Painel de solicitações de todas as obras — só administrador (06/10/2026)."""

import pytest

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
SENHA = "senha-pnl-12345"


def _usuario(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@pnl.teste.com.br"
    r = cliente.post(
        "/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA}, headers=admin
    )
    assert r.status_code == 201, r.text
    cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": r.json()["id"], "papel": papel}, headers=admin,
    )
    return autenticar(cliente, email, SENHA)


def _doc_liberado(cliente, admin, obra, prancha):
    codigo = obra["codigo"]
    r = enviar_arquivo(cliente, admin, obra["id"], f"{codigo}-ARQ-PE-{prancha}-R00.pdf", PDF,
                       titulo=f"Prancha {prancha}")
    cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={}, headers=admin)
    itens = cliente.get(
        f"/obras/{obra['id']}/documentos?busca={codigo}-ARQ-PE-{prancha}", headers=admin
    ).json()["itens"]
    return itens[0]["id"]


@pytest.fixture(scope="module")
def cenario(cliente, admin):
    obras = [
        cliente.post("/obras", json={"codigo": c, "nome": f"Obra {c}"}, headers=admin).json()
        for c in ("PNA", "PNB")
    ]
    campo = _usuario(cliente, admin, obras[0], "campo", "obra")
    coord = _usuario(cliente, admin, obras[0], "coord", "coordenador")
    doc_a = _doc_liberado(cliente, admin, obras[0], "001")
    doc_b = _doc_liberado(cliente, admin, obras[1], "001")
    aberto = cliente.post(
        f"/documentos/{doc_a}/solicitacoes",
        json={"descricao": "Mudar o ralo de lugar, está na viga."}, headers=campo,
    ).json()
    autorizado = cliente.post(
        f"/documentos/{doc_b}/solicitacoes",
        json={"descricao": "Compatibilizar com o ar-condicionado."}, headers=admin,
    ).json()
    return {"obras": obras, "campo": campo, "coord": coord, "doc_a": doc_a,
            "aberto": aberto, "autorizado": autorizado}


def test_admin_ve_os_pedidos_de_todas_as_obras(cliente, admin, cenario):
    lista = cliente.get("/solicitacoes", headers=admin).json()
    por_id = {s["id"]: s for s in lista}
    a = por_id[cenario["aberto"]["id"]]
    assert a["status"] == "aberta"
    assert a["obra_codigo"] == "PNA"
    assert a["documento_id"] == cenario["doc_a"]
    assert a["documento_codigo"] == "PNA-ARQ-PE-001"
    assert a["documento_titulo"] == "Prancha 001"
    assert a["revisao_numero"] == "00"
    assert a["criada_por"]["nome"] == "Campo"
    assert por_id[cenario["autorizado"]["id"]]["obra_codigo"] == "PNB"
    # Mais recente primeiro.
    ids = [s["id"] for s in lista]
    assert ids.index(cenario["autorizado"]["id"]) < ids.index(cenario["aberto"]["id"])


def test_filtros_por_situacao_e_por_obra(cliente, admin, cenario):
    so_abertas = cliente.get("/solicitacoes?status=aberta", headers=admin).json()
    assert {s["status"] for s in so_abertas} == {"aberta"}
    em_aberto = cliente.get("/solicitacoes?status=aberta&status=autorizada", headers=admin).json()
    assert {cenario["aberto"]["id"], cenario["autorizado"]["id"]} <= {s["id"] for s in em_aberto}
    da_obra = cliente.get(f"/solicitacoes?obra_id={cenario['obras'][1]['id']}", headers=admin).json()
    assert {s["obra_codigo"] for s in da_obra} == {"PNB"}


def test_contador_conta_os_que_esperam_autorizacao(cliente, admin, cenario):
    antes = cliente.get("/solicitacoes/contagem", headers=admin).json()["aguardando"]
    assert antes >= 1
    cliente.post(f"/solicitacoes/{cenario['aberto']['id']}/autorizar", headers=admin)
    assert cliente.get("/solicitacoes/contagem", headers=admin).json()["aguardando"] == antes - 1


def test_so_administrador(cliente, cenario):
    for quem in ("campo", "coord"):
        assert cliente.get("/solicitacoes", headers=cenario[quem]).status_code == 403
        assert cliente.get("/solicitacoes/contagem", headers=cenario[quem]).status_code == 403
