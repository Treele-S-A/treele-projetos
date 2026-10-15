"""Avisos opcionais para o coordenador e liberação em lote (TREELE, 15/10/2026).

Em volume, não vale mandar centenas de e-mails: o coordenador escolhe se
avisa ao enviar arquivo e ao liberar para obra. O projetista e a obra não
escolhem — o envio do projetista e o pedido da obra avisam sempre.
"""

import pytest

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
DWG = b"AC1032" + b"\x00" * 200
SENHA = "senha-lote-12345"
OBRA = "LTE"


def _usuario(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@lote.teste.com.br"
    r = cliente.post("/usuarios", json={"nome": f"{apelido.title()} Lima", "email": email, "senha": SENHA},
                     headers=admin)
    assert r.status_code == 201, r.text
    m = cliente.post(f"/obras/{obra['id']}/membros", json={"usuario_id": r.json()["id"], "papel": papel},
                     headers=admin)
    assert m.status_code in (200, 201), m.text
    return autenticar(cliente, email, SENHA)


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": OBRA, "nome": "Obra lote"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def p(cliente, admin, obra):
    return {
        "coord": _usuario(cliente, admin, obra, "coordlte", "coordenador"),
        "coord2": _usuario(cliente, admin, obra, "coorddois", "coordenador"),
        "proj": _usuario(cliente, admin, obra, "projlte", "projetista"),
        "campo": _usuario(cliente, admin, obra, "campolte", "obra"),
    }


def _nao_lidas(cliente, cab):
    return [a for a in cliente.get("/notificacoes", headers=cab).json() if not a["lida"]]


def _limpar(cliente, *cabs):
    for cab in cabs:
        assert cliente.post("/notificacoes/lidas", headers=cab).status_code == 204


def _enviar(cliente, cab, obra, prancha, conteudo=PDF, ext="pdf", **kw):
    r = enviar_arquivo(cliente, cab, obra["id"], f"{OBRA}-ARQ-PE-{prancha}-R00.{ext}", conteudo, **kw)
    assert r.status_code == 200, r.text
    return r.json()["revisao"]


# ------------------------------------------------------------ envio


def test_coordenador_envia_sem_avisar(cliente, admin, obra, p):
    _limpar(cliente, admin, *p.values())
    _enviar(cliente, p["coord"], obra, "001", avisar=False)
    assert _nao_lidas(cliente, p["coord2"]) == []


def test_coordenador_envia_avisando(cliente, admin, obra, p):
    _limpar(cliente, admin, *p.values())
    _enviar(cliente, p["coord"], obra, "002", avisar=True)
    assert [a["tipo"] for a in _nao_lidas(cliente, p["coord2"])] == ["revisao_enviada"]


def test_projetista_nao_cala_o_aviso(cliente, admin, obra, p):
    _limpar(cliente, admin, *p.values())
    _enviar(cliente, p["proj"], obra, "003", avisar=False)
    assert [a["tipo"] for a in _nao_lidas(cliente, p["coord"])] == ["revisao_enviada"]


# ------------------------------------------------------------ liberação avulsa


def test_liberar_sem_avisar_a_obra(cliente, admin, obra, p):
    rev = _enviar(cliente, p["proj"], obra, "004")
    _limpar(cliente, admin, *p.values())

    r = cliente.post(f"/revisoes/{rev['id']}/publicar", json={"avisar": False}, headers=p["coord"])

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "liberado_para_obra"
    assert _nao_lidas(cliente, p["campo"]) == []
    evento = cliente.get(f"/obras/{obra['id']}/eventos", headers=admin).json()["itens"][0]
    assert evento["acao"] == "revisao_publicada"
    assert evento["detalhes"]["avisos"] is False


def test_liberar_avisando_a_obra_e_o_padrao(cliente, admin, obra, p):
    rev = _enviar(cliente, p["proj"], obra, "005")
    _limpar(cliente, admin, *p.values())
    assert cliente.post(f"/revisoes/{rev['id']}/publicar", json={}, headers=p["coord"]).status_code == 200
    assert [a["tipo"] for a in _nao_lidas(cliente, p["campo"])] == ["revisao_liberada"]


# ------------------------------------------------------------ lote


def test_lote_libera_o_que_pode_e_explica_o_resto(cliente, admin, obra, p):
    a = _enviar(cliente, p["proj"], obra, "010")
    b = _enviar(cliente, p["proj"], obra, "011")
    so_dwg = _enviar(cliente, p["proj"], obra, "012", conteudo=DWG, ext="dwg")
    _limpar(cliente, admin, *p.values())

    r = cliente.post("/revisoes/liberar-lote", json={
        "revisao_ids": [a["id"], b["id"], so_dwg["id"], 999999],
        "observacao": "Liberado em lote na migração.",
        "avisar": False,
    }, headers=p["coord"])

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert sorted(x["revisao_id"] for x in corpo["liberadas"]) == sorted([a["id"], b["id"]])
    recusadas = {x["revisao_id"]: x for x in corpo["recusadas"]}
    assert set(recusadas) == {so_dwg["id"], 999999}
    assert any("PDF" in m for m in recusadas[so_dwg["id"]]["motivos"])
    assert recusadas[999999]["motivos"] == ["Revisão não encontrada."]

    for rev in (a, b):
        detalhe = cliente.get(f"/revisoes/{rev['id']}", headers=p["coord"]).json()
        assert detalhe["status"] == "liberado_para_obra"
        assert detalhe["observacao"] == "Liberado em lote na migração."
    assert cliente.get(f"/revisoes/{so_dwg['id']}", headers=p["coord"]).json()["status"] == "em_revisao"
    assert _nao_lidas(cliente, p["campo"]) == []


def test_lote_avisando_manda_um_aviso_por_revisao(cliente, admin, obra, p):
    a = _enviar(cliente, p["proj"], obra, "020")
    b = _enviar(cliente, p["proj"], obra, "021")
    _limpar(cliente, admin, *p.values())

    r = cliente.post("/revisoes/liberar-lote", json={"revisao_ids": [a["id"], b["id"]], "avisar": True},
                     headers=p["coord"])

    assert r.status_code == 200, r.text
    assert len(r.json()["liberadas"]) == 2
    assert [x["tipo"] for x in _nao_lidas(cliente, p["campo"])] == ["revisao_liberada", "revisao_liberada"]


def test_lote_so_para_quem_libera(cliente, obra, p):
    a = _enviar(cliente, p["proj"], obra, "030")
    r = cliente.post("/revisoes/liberar-lote", json={"revisao_ids": [a["id"]]}, headers=p["proj"])
    assert r.status_code == 200, r.text
    assert r.json()["liberadas"] == []
    assert "coordenador" in r.json()["recusadas"][0]["motivos"][0]
    assert cliente.get(f"/revisoes/{a['id']}", headers=p["proj"]).json()["status"] == "em_revisao"


def test_lote_fecha_os_pedidos_autorizados(cliente, admin, obra, p):
    r00 = _enviar(cliente, p["proj"], obra, "040")
    liberou = cliente.post(f"/revisoes/{r00['id']}/publicar", json={"avisar": False}, headers=p["coord"])
    assert liberou.status_code == 200, liberou.text
    r01 = enviar_arquivo(cliente, p["proj"], obra["id"], f"{OBRA}-ARQ-PE-040-R01.pdf", PDF,
                         autorizar_com=p["coord"])
    assert r01.status_code == 200, r01.text

    r = cliente.post("/revisoes/liberar-lote",
                     json={"revisao_ids": [r01.json()["revisao"]["id"]], "avisar": False}, headers=p["coord"])

    assert len(r.json()["liberadas"]) == 1
    doc = cliente.get(f"/obras/{obra['id']}/documentos?busca={OBRA}-ARQ-PE-040", headers=p["coord"]).json()["itens"][0]
    detalhe = cliente.get(f"/documentos/{doc['id']}", headers=p["coord"]).json()
    assert [s["status"] for s in detalhe["solicitacoes"]] == ["atendida"]
    assert cliente.get(f"/revisoes/{r00['id']}", headers=p["coord"]).json()["status"] == "obsoleto"
