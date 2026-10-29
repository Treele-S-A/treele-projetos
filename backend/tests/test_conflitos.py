"""Conflitos entre disciplinas guardados no servidor (TREELE, 22/10/2026): o
mesmo conflito é reconhecido entre rodadas pelos GlobalIds, a situação segue
as regras (novo, ativo, aprovado, resolvido) e cada papel faz a sua parte."""

import pytest
from sqlalchemy import select

from .conftest import autenticar, enviar_arquivo

SENHA = "senha-conflito-12345"
IFC = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n" + b" " * 300
CONFIG = {
    "a": {"disciplinas": ["HID"], "categorias": [], "excluir": ["IFCWALL"]},
    "b": {"disciplinas": ["EST"], "categorias": ["IFCCOLUMN", "IFCBEAM"]},
    "modo": "interferencia", "tolerancia": 0.01, "folga": 0.05, "ignorarMesmoModelo": True,
}


def _pessoa(cliente, admin, obra, apelido, papel, comercial=False):
    email = f"{apelido}@conflito.teste.com.br"
    u = cliente.post("/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA,
                                        "comercial": comercial}, headers=admin).json()
    if papel:
        cliente.post(f"/obras/{obra['id']}/membros", json={"usuario_id": u["id"], "papel": papel}, headers=admin)
    return autenticar(cliente, email, SENHA)


@pytest.fixture(scope="module")
def c(cliente, admin):
    obra = cliente.post("/obras", json={"codigo": "CFL", "nome": "Obra conflitos", "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"}, headers=admin).json()
    outra = cliente.post("/obras", json={"codigo": "CFX", "nome": "Outra", "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"}, headers=admin).json()
    coord = _pessoa(cliente, admin, obra, "coordcfl", "coordenador")
    proj = _pessoa(cliente, admin, obra, "projcfl", "projetista")
    campo = _pessoa(cliente, admin, obra, "campocfl", "obra")
    comercial = _pessoa(cliente, admin, obra, "comcfl", None, comercial=True)
    ids = {}
    for disc in ("EST", "HID"):
        r = enviar_arquivo(cliente, proj, obra["id"], f"CFL-{disc}-PE-MOD-R00.ifc", IFC).json()
        assert cliente.post(f"/revisoes/{r['revisao']['id']}/publicar", json={"avisar": False},
                            headers=coord).status_code == 200
        ids[disc] = r["arquivo"]["id"]
    ele = enviar_arquivo(cliente, proj, obra["id"], "CFL-ELE-PE-MOD-R00.ifc", IFC).json()  # em revisão
    fora = enviar_arquivo(cliente, admin, outra["id"], "CFX-HID-PE-MOD-R00.ifc", IFC).json()
    return {"obra": obra, "coord": coord, "proj": proj, "campo": campo, "comercial": comercial,
            "est": ids["EST"], "hid": ids["HID"], "ele": ele["arquivo"]["id"], "fora": fora["arquivo"]["id"]}


def _achado(c, guids_a, guid_b, **extra):
    return {"arquivo_a_id": c["hid"], "arquivo_b_id": c["est"], "guids_a": guids_a, "guid_b": guid_b,
            "categoria_a": "IFCFLOWSEGMENT", "categoria_b": "IFCBEAM", "nome_a": "Tubo 100", "nome_b": "V12",
            "centro": [1, 2, 3], "caixa_min": [0, 1, 2], "caixa_max": [2, 3, 4], "medida": 0.08, **extra}


def _rodada(cliente, cab, conjunto_id, arquivos, achados):
    return cliente.post(f"/conjuntos-conflito/{conjunto_id}/rodadas",
                        json={"arquivos": arquivos, "achados": achados}, headers=cab)


@pytest.fixture(scope="module")
def conjunto(cliente, c):
    r = cliente.post(f"/obras/{c['obra']['id']}/conjuntos-conflito",
                     json={"nome": "Instalações × pilares e vigas", "pronto": "instalacoes-estrutura",
                           "config": CONFIG}, headers=c["proj"])
    assert r.status_code == 201, r.text
    return r.json()


def test_pronto_qualquer_um_cria_uma_vez_e_o_montado_e_do_coordenador(cliente, c, conjunto):
    obra = c["obra"]["id"]
    de_novo = cliente.post(f"/obras/{obra}/conjuntos-conflito",
                           json={"nome": "Outro nome", "pronto": "instalacoes-estrutura", "config": CONFIG},
                           headers=c["campo"])
    assert de_novo.json()["id"] == conjunto["id"]
    montado = {"nome": "HID × lajes", "config": CONFIG}
    assert cliente.post(f"/obras/{obra}/conjuntos-conflito", json=montado, headers=c["proj"]).status_code == 403
    r = cliente.post(f"/obras/{obra}/conjuntos-conflito", json=montado, headers=c["coord"])
    assert r.status_code == 201 and r.json()["pronto"] is None
    assert cliente.patch(f"/conjuntos-conflito/{r.json()['id']}", json={**montado, "nome": "x"},
                         headers=c["proj"]).status_code == 403
    assert cliente.delete(f"/conjuntos-conflito/{r.json()['id']}", headers=c["coord"]).status_code == 204
    # O comercial não vê conflitos.
    assert cliente.get(f"/obras/{obra}/conjuntos-conflito", headers=c["comercial"]).status_code == 403


def test_situacao_segue_as_rodadas(cliente, c, conjunto):
    cid, cena = conjunto["id"], [c["est"], c["hid"]]
    r = _rodada(cliente, c["proj"], cid, cena, [_achado(c, ["t1", "t2"], "v12"), _achado(c, ["t9"], "p33")])
    assert r.status_code == 200, r.text
    corpo = r.json()
    primeiro, segundo = corpo["ids"]
    assert {x["id"]: x["status"] for x in corpo["conflitos"]} == {primeiro: "novo", segundo: "novo"}
    assert corpo["conjunto"]["ultima_rodada"]["novos"] == 2

    # O tubo foi agrupado de outro jeito (t2 e t3): é o mesmo conflito, agora
    # ativo. O do P33 não apareceu, com os dois modelos na cena: resolvido.
    r = _rodada(cliente, c["proj"], cid, cena, [_achado(c, ["t3", "t2"], "v12", medida=0.05)])
    corpo = r.json()
    assert corpo["ids"] == [primeiro]
    por_id = {x["id"]: x for x in corpo["conflitos"]}
    assert por_id[primeiro]["status"] == "ativo" and por_id[primeiro]["medida"] == 0.05
    assert por_id[primeiro]["documento_a"] == "CFL-HID-PE-MOD" and por_id[primeiro]["disciplina_b"] == "EST"
    assert por_id[segundo]["status"] == "resolvido" and por_id[segundo]["resolvido_em"]
    assert corpo["conjunto"]["ultima_rodada"]["resolvidos"] == 1

    # Sem a estrutura na cena, nada se resolve.
    r = _rodada(cliente, c["proj"], cid, [c["hid"]], [])
    assert {x["id"]: x["status"] for x in r.json()["conflitos"]}[primeiro] == "ativo"

    # O do P33 voltou: reaberto como ativo.
    r = _rodada(cliente, c["proj"], cid, cena, [_achado(c, ["t3"], "v12"), _achado(c, ["t9"], "p33")])
    por_id = {x["id"]: x for x in r.json()["conflitos"]}
    assert por_id[segundo]["status"] == "ativo" and por_id[segundo]["resolvido_em"] is None
    assert r.json()["conjunto"]["ultima_rodada"]["reabertos"] == 1
    assert r.json()["conjunto"]["contagem"] == {"ativo": 2}


def test_aprovar_e_do_coordenador_com_justificativa(cliente, c, conjunto):
    cid, cena = conjunto["id"], [c["est"], c["hid"]]
    alvo = _rodada(cliente, c["proj"], cid, cena, [_achado(c, ["t3"], "v12"), _achado(c, ["t9"], "p33")]).json()["ids"][0]
    assert cliente.patch(f"/conflitos/{alvo}", json={"status": "aprovado", "justificativa": "Furo previsto"},
                         headers=c["proj"]).status_code == 403
    assert cliente.patch(f"/conflitos/{alvo}", json={"status": "aprovado"}, headers=c["coord"]).status_code == 422
    r = cliente.patch(f"/conflitos/{alvo}", json={"status": "aprovado", "justificativa": "Furo previsto na V12"},
                      headers=c["coord"])
    assert r.status_code == 200 and r.json()["status"] == "aprovado" and r.json()["atualizado_por"] == "Coordcfl"
    # Aprovado não volta a ativo quando aparece, nem vira resolvido quando some.
    r = _rodada(cliente, c["proj"], cid, cena, [_achado(c, ["t3"], "v12")])
    assert {x["id"]: x["status"] for x in r.json()["conflitos"]}[alvo] == "aprovado"
    r = _rodada(cliente, c["proj"], cid, cena, [])
    assert {x["id"]: x["status"] for x in r.json()["conflitos"]}[alvo] == "aprovado"
    r = cliente.patch(f"/conflitos/{alvo}", json={"status": "ativo"}, headers=c["coord"])
    assert r.json()["status"] == "ativo" and r.json()["justificativa"] is None


def test_vista_ligada_ao_conflito_e_resumo_da_obra(cliente, c, conjunto):
    cid, cena = conjunto["id"], [c["est"], c["hid"]]
    alvo = _rodada(cliente, c["proj"], cid, cena, [_achado(c, ["t3"], "v12")]).json()["ids"][0]
    vista = cliente.post(f"/obras/{c['obra']['id']}/vistas",
                         json={"titulo": "Conflito V12", "arquivos": cena,
                               "camera": {"posicao": [1, 1, 1], "alvo": [0, 0, 0]}},
                         headers=c["proj"]).json()["vista"]
    r = cliente.patch(f"/conflitos/{alvo}", json={"vista_id": vista["id"]}, headers=c["proj"])
    assert r.status_code == 200 and r.json()["vista_id"] == vista["id"]
    resumo = cliente.get(f"/obras/{c['obra']['id']}/conflitos/resumo", headers=c["campo"]).json()
    par = next(p for p in resumo["pares"] if p["disciplina_a"] == "HID" and p["disciplina_b"] == "EST")
    assert par["ativo"] >= 1 and resumo["abertos"] == par["novo"] + par["ativo"]
    # O mesmo par de peças num segundo conjunto não conta de novo.
    outro = cliente.post(f"/obras/{c['obra']['id']}/conjuntos-conflito",
                         json={"nome": "Com folga", "config": {**CONFIG, "modo": "folga"}}, headers=c["coord"]).json()
    _rodada(cliente, c["proj"], outro["id"], cena, [_achado(c, ["t3"], "v12")])
    depois = cliente.get(f"/obras/{c['obra']['id']}/conflitos/resumo", headers=c["campo"]).json()
    assert depois["abertos"] == resumo["abertos"]


def test_rodada_so_com_modelos_da_cena_que_a_pessoa_abre(cliente, c, conjunto):
    cid = conjunto["id"]
    # Achado de um modelo que não está na lista da cena.
    r = _rodada(cliente, c["proj"], cid, [c["hid"]], [_achado(c, ["t1"], "v1")])
    assert r.status_code == 422
    # Modelo de outra obra.
    assert _rodada(cliente, c["proj"], cid, [c["fora"]], []).status_code == 422
    # A obra não abre o que está em revisão.
    assert _rodada(cliente, c["campo"], cid, [c["ele"]], []).status_code in (403, 404)


# ------------------------------------------------------- chat (22/10/2026)


def test_chat_consulta_conflitos_com_as_regras_da_tela(cliente, c, conjunto):
    from app.db import SessionLocal
    from app.models import Usuario
    from app.services.chat_ferramentas import Ferramentas, descrever, resumir

    cena = [c["est"], c["hid"]]
    _rodada(cliente, c["proj"], conjunto["id"], cena,
            [_achado(c, ["t3"], "v12"), _achado(c, ["t9"], "p33", nome_b="P33")])
    db = SessionLocal()
    try:
        proj = db.scalar(select(Usuario).where(Usuario.email == "projcfl@conflito.teste.com.br"))
        r = Ferramentas(db, proj).executar("consultar_conflitos", {"obra": "CFL", "disciplina": "hid"})
        obra = r["conflitos_obras"][0]
        assert obra["abertos"] >= 2 and "HID × EST" in obra["por_par_de_disciplinas"]
        assert obra["conjuntos"][0]["feita_por"] == "Projcfl" and obra["conjuntos"][0]["ultima_deteccao"]
        alvo = next(x for x in obra["conflitos"] if x["peca_b"].endswith("P33"))
        assert alvo["documento_a"] == "CFL-HID-PE-MOD R00" and alvo["entra_cm"] == 8.0 and alvo["cota_m"] == 2
        assert alvo["link_documento_b"].startswith("/documentos/")
        # Busca pelo nome da peça.
        r = Ferramentas(db, proj).executar("consultar_conflitos", {"obra": "CFL", "busca": "p33", "listar": True})
        assert [x["peca_b"] for x in r["conflitos_obras"][0]["conflitos"]] == ["Viga: P33"]
        assert resumir(r) == "1 conflito encontrado"  # o da busca, não o total da obra
        com = db.scalar(select(Usuario).where(Usuario.email == "comcfl@conflito.teste.com.br"))
        assert "erro" in Ferramentas(db, com).executar("consultar_conflitos", {"obra": "CFL"})
    finally:
        db.close()
    assert descrever("consultar_conflitos", {"obra": "SER", "disciplina": "HID"}) == (
        "Consultando os conflitos abertos (HID) na obra SER"
    )


def test_conjunto_guarda_o_filtro_por_nome(cliente, c):
    config = {**CONFIG, "a": {**CONFIG["a"], "excluirNomes": ["Flexível", "Embutido"]}}
    r = cliente.post(f"/obras/{c['obra']['id']}/conjuntos-conflito",
                     json={"nome": "Sem eletroduto flexível", "config": config}, headers=c["coord"])
    assert r.status_code == 201, r.text
    assert r.json()["config"]["a"]["excluirNomes"] == ["Flexível", "Embutido"]


def test_resumo_da_obra_para_o_quadro(cliente, c, conjunto):
    cena = [c["est"], c["hid"]]
    _rodada(cliente, c["proj"], conjunto["id"], cena, [_achado(c, ["t3"], "v12"), _achado(c, ["t9"], "p33")])
    r = cliente.get(f"/obras/{c['obra']['id']}/conflitos/resumo", headers=c["campo"]).json()
    assert r["abertos"] >= 2 and r["novos"] + sum(p["ativo"] for p in r["pares"]) == r["abertos"]
    docs = {d["codigo"]: d for d in r["documentos"]}
    assert docs["CFL-HID-PE-MOD"]["abertos"] == docs["CFL-EST-PE-MOD"]["abertos"] >= 2
    assert r["ultima_deteccao"]["feita_por"] == "Projcfl"
    # Os IFC liberados que a obra pode abrir (EST e HID).
    assert r["arquivos_3d"] == [c["est"], c["hid"]]  # a estrutura primeiro
