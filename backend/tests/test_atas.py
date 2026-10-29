"""Ata de análise crítica antes de liberar para obra (TREELE, 29/10/2026 —
SIAC). O checklist PRO-FL-005 da disciplina, respondido uma vez por revisão;
uma ata cobre as revisões da mesma disciplina liberadas juntas; qualquer "N"
impede a liberação."""

import pytest

from app.config import settings

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
SENHA = "senha-ata-12345"
OBRA = "ATA"


@pytest.fixture(autouse=True)
def _ata_obrigatoria(monkeypatch):
    monkeypatch.setattr(settings, "ata_analise_obrigatoria", True)


def _usuario(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@ata.teste.com.br"
    r = cliente.post(
        "/usuarios", json={"nome": f"{apelido.title()} Lima", "email": email, "senha": SENHA},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    m = cliente.post(
        f"/obras/{obra['id']}/membros", json={"usuario_id": r.json()["id"], "papel": papel},
        headers=admin,
    )
    assert m.status_code in (200, 201), m.text
    return autenticar(cliente, email, SENHA)


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": OBRA, "nome": "Obra da ata"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def p(cliente, admin, obra):
    return {
        "coord": _usuario(cliente, admin, obra, "coordata", "coordenador"),
        "proj": _usuario(cliente, admin, obra, "projata", "projetista"),
    }


def _enviar(cliente, cab, obra, disc, prancha):
    r = enviar_arquivo(cliente, cab, obra["id"], f"{OBRA}-{disc}-PE-{prancha}-R00.pdf", PDF)
    assert r.status_code == 200, r.text
    return r.json()["revisao"]


def _respostas(grupo, resposta="S", excecoes=None):
    excecoes = excecoes or {}
    return [
        {"id": i["id"], "resposta": excecoes.get(i["id"], (resposta, None))[0],
         "comentario": excecoes.get(i["id"], (resposta, None))[1]}
        for g in grupo["formulario"]["grupos"] for i in g["itens"]
    ]


def test_formulario_da_disciplina_e_rgf_sempre(cliente, p, obra):
    hid = _enviar(cliente, p["proj"], obra, "HID", "001")
    gas = _enviar(cliente, p["proj"], obra, "GAS", "001")
    grupos = cliente.post("/atas/pendentes", json={"revisao_ids": [hid["id"], gas["id"]]}, headers=p["coord"]).json()
    por = {g["disciplina"]: g["formulario"] for g in grupos}
    # Hidráulica: o bloco da hidráulica, com os itens de compatibilização dele.
    titulos = [g["titulo"] for g in por["HID"]["grupos"]]
    assert titulos[0] == "Representação gráfica"
    assert "Hidráulica" in titulos and "Estrutura" in titulos and "Desempenho (NBR 15575)" in titulos
    assert por["HID"]["blocos"] == ["Hidráulica"]
    itens_hid = [i["texto"] for g in por["HID"]["grupos"] for i in g["itens"]]
    assert any("passagens em vigas e lajes" in t for t in itens_hid)
    assert not any("caixilhos" in t.lower() for t in itens_hid)  # é da arquitetura
    # Gás não tem bloco na planilha: só a representação gráfica.
    assert [g["titulo"] for g in por["GAS"]["grupos"]] == ["Representação gráfica"]


def test_liberar_sem_ata_e_recusado(cliente, p, obra):
    rev = _enviar(cliente, p["proj"], obra, "ELE", "001")
    v = cliente.get(f"/revisoes/{rev['id']}/verificar", headers=p["coord"]).json()
    assert v["falta_ata"] is True and v["pode_publicar"] is False and v["impedimentos"] == []
    r = cliente.post(f"/revisoes/{rev['id']}/publicar", json={}, headers=p["coord"])
    assert r.status_code == 409
    assert any("ata de análise crítica" in e for e in r.json()["detail"]["erros"])


def test_ata_conforme_libera_e_fica_ligada_as_revisoes(cliente, p, obra):
    r1 = _enviar(cliente, p["proj"], obra, "ELE", "002")
    r2 = _enviar(cliente, p["proj"], obra, "ELE", "003")
    [grupo] = cliente.post("/atas/pendentes", json={"revisao_ids": [r1["id"], r2["id"]]}, headers=p["coord"]).json()
    assert [x["id"] for x in grupo["revisoes"]] == [r1["id"], r2["id"]]

    # Incompleta: recusa e diz o que falta.
    incompleta = _respostas(grupo)[1:]
    r = cliente.post("/atas", json={"revisao_ids": [r1["id"], r2["id"]], "respostas": incompleta}, headers=p["coord"])
    assert r.status_code == 422 and "sem resposta" in r.json()["detail"]["erros"][0]

    r = cliente.post(
        "/atas",
        json={"revisao_ids": [r1["id"], r2["id"]], "respostas": _respostas(grupo, "NA"), "observacoes": "Ok."},
        headers=p["coord"],
    )
    assert r.status_code == 201, r.text
    ata = r.json()
    assert ata["resultado"] == "conforme" and ata["codigo"].startswith("ATA-ATA-")
    assert [x["documento"] for x in ata["revisoes"]] == ["ATA-ELE-PE-002", "ATA-ELE-PE-003"]

    # Uma ata por revisão: não ganha outra.
    r = cliente.post("/atas", json={"revisao_ids": [r1["id"]], "respostas": _respostas(grupo)}, headers=p["coord"])
    assert r.status_code == 409

    lote = cliente.post("/revisoes/liberar-lote", json={"revisao_ids": [r1["id"], r2["id"]]}, headers=p["coord"]).json()
    assert len(lote["liberadas"]) == 2, lote
    doc = cliente.get(f"/revisoes/{r1['id']}", headers=p["coord"]).json()
    assert doc["status"] == "liberado_para_obra" and doc["ata"]["codigo"] == ata["codigo"]

    # Na lista e no detalhe, para quem é da obra.
    lista = cliente.get(f"/atas?obra_id={obra['id']}", headers=p["proj"]).json()
    assert ata["id"] in [a["id"] for a in lista["itens"]]
    detalhe = cliente.get(f"/atas/{ata['id']}", headers=p["proj"]).json()
    assert detalhe["itens"][0]["resposta"] == "NA" and detalhe["observacoes"] == "Ok."


def test_item_n_exige_comentario_e_impede_liberar(cliente, p, obra):
    rev = _enviar(cliente, p["proj"], obra, "HID", "002")
    [grupo] = cliente.post("/atas/pendentes", json={"revisao_ids": [rev["id"]]}, headers=p["coord"]).json()
    primeiro = grupo["formulario"]["grupos"][0]["itens"][0]["id"]

    r = cliente.post("/atas", json={"revisao_ids": [rev["id"]], "respostas": _respostas(grupo, "S", {primeiro: ("N", "")})}, headers=p["coord"])
    assert r.status_code == 422 and "comentário" in r.json()["detail"]["erros"][0]

    r = cliente.post(
        "/atas",
        json={"revisao_ids": [rev["id"]], "respostas": _respostas(grupo, "S", {primeiro: ("N", "Nome fora do padrão.")})},
        headers=p["coord"],
    )
    assert r.status_code == 201 and r.json()["resultado"] == "nao_conforme" and r.json()["nao_conformes"] == 1

    r = cliente.post(f"/revisoes/{rev['id']}/publicar", json={}, headers=p["coord"])
    assert r.status_code == 409 and any("não conformes" in e for e in r.json()["detail"]["erros"])
    # Refazer a análise é possível: a não conforme não conta como "a" ata.
    [de_novo] = cliente.post("/atas/pendentes", json={"revisao_ids": [rev["id"]]}, headers=p["coord"]).json()
    r = cliente.post("/atas", json={"revisao_ids": [rev["id"]], "respostas": _respostas(de_novo)}, headers=p["coord"])
    assert r.status_code == 201 and r.json()["resultado"] == "conforme"
    assert cliente.post(f"/revisoes/{rev['id']}/publicar", json={}, headers=p["coord"]).status_code == 200


def test_so_quem_libera_faz_a_ata_e_uma_disciplina_por_ata(cliente, p, obra):
    a = _enviar(cliente, p["proj"], obra, "ARQ", "001")
    b = _enviar(cliente, p["proj"], obra, "EST", "001")
    [ga, gb] = cliente.post("/atas/pendentes", json={"revisao_ids": [a["id"], b["id"]]}, headers=p["coord"]).json()
    r = cliente.post("/atas", json={"revisao_ids": [a["id"]], "respostas": _respostas(ga)}, headers=p["proj"])
    assert r.status_code == 403
    r = cliente.post(
        "/atas", json={"revisao_ids": [a["id"], b["id"]], "respostas": _respostas(ga) + _respostas(gb)},
        headers=p["coord"],
    )
    assert r.status_code == 422
    # O projetista não vê pendências de ata (não libera).
    assert cliente.post("/atas/pendentes", json={"revisao_ids": [a["id"]]}, headers=p["proj"]).json() == []
