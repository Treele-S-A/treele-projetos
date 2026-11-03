"""Cronograma de projetos em Gantt — PRO-FL-001 (TREELE, 03/11/2026): datas
pelas predecessoras em dias úteis, caminho crítico, edição e quem acessa."""

from datetime import date

import pytest

from app.services.cronograma import MODELO, data, indice

from .conftest import autenticar

SENHA = "senha-crono-12345"


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post(
        "/obras", json={"codigo": "CRN", "nome": "Obra cronograma", "endereco": "Rua A, 1 – Curitiba – PR"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _pessoa(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@crn.teste.com.br"
    r = cliente.post("/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA}, headers=admin)
    assert r.status_code == 201, r.text
    if papel:
        m = cliente.post(f"/obras/{obra['id']}/membros", json={"usuario_id": r.json()["id"], "papel": papel}, headers=admin)
        assert m.status_code in (200, 201), m.text
    return autenticar(cliente, email, SENHA)


def test_dias_uteis():
    sexta, segunda = date(2026, 11, 6), date(2026, 11, 9)
    assert indice(segunda) - indice(sexta) == 1
    assert indice(date(2026, 11, 7)) == indice(segunda)  # sábado conta como a segunda seguinte
    assert data(indice(sexta) + 1) == segunda


def test_modelo_sem_vinculo_solto():
    chaves = [i[0] for _, itens in MODELO for i in itens]
    assert len(chaves) == len(set(chaves))
    for _, itens in MODELO:
        for chave, *_, preds in itens:
            for p, tipo, _ in preds:
                assert p in chaves and p != chave and tipo in ("TI", "II", "TT")


def test_cria_pelo_modelo_e_calcula(cliente, admin, obra):
    url = f"/obras/{obra['id']}/cronograma"
    assert cliente.get(url, headers=admin).json()["existe"] is False
    r = cliente.post(url, json={"inicio": "2026-11-02", "modelo": True}, headers=admin)
    assert r.status_code == 201, r.text
    c = r.json()
    total = sum(len(itens) for _, itens in MODELO)
    assert len(c["atividades"]) == total and [a["numero"] for a in c["atividades"]] == list(range(1, total + 1))
    por = {a["nome"]: a for a in c["atividades"]}
    # Marco no início; o que vem depois dele começa no mesmo dia.
    assert por["Reunião de passagem (Incorporação → Projetos)"]["inicio"] == "2026-11-02"
    topo = por["Levantamento topográfico planialtimétrico"]
    assert topo["inicio"] == "2026-11-02" and topo["termino"] == "2026-11-13"  # 10 dias úteis
    # TI: o estudo preliminar começa no dia útil seguinte ao fim da topografia.
    assert por["Estudo preliminar de implantação"]["inicio"] == "2026-11-16"
    # II +10: a estrutura começa 10 dias úteis depois do início do arquitetônico.
    arq, est = por["Projeto arquitetônico"], por["Projeto estrutural"]
    assert indice(date.fromisoformat(est["inicio"])) - indice(date.fromisoformat(arq["inicio"])) >= 10
    # Gás: II com o ante-projeto de incêndio (o vínculo do macrofluxo).
    assert por["Projeto de rede de gás"]["inicio"] == por["Ante-projeto de incêndio"]["inicio"]
    # O caminho crítico chega ao fim do projeto e tem folga zero.
    criticas = [a for a in c["atividades"] if a["critica"]]
    assert criticas and all(a["folga"] <= 0 for a in criticas)
    assert max(a["termino"] for a in criticas) == c["termino"]
    assert cliente.post(url, json={"inicio": "2026-11-02"}, headers=admin).status_code == 409


def test_edita_arrasta_e_vincula(cliente, admin, obra):
    url = f"/obras/{obra['id']}/cronograma"
    c = cliente.get(url, headers=admin).json()
    por = {a["nome"]: a for a in c["atividades"]}
    topo, ep = por["Levantamento topográfico planialtimétrico"], por["Estudo preliminar de implantação"]

    # Mais duração empurra a sucessora.
    c = cliente.patch(f"{url}/atividades/{topo['id']}", json={"duracao": 15, "progresso": 40}, headers=admin).json()
    por = {a["id"]: a for a in c["atividades"]}
    assert por[topo["id"]]["termino"] == "2026-11-20" and por[topo["id"]]["progresso"] == 40
    assert por[ep["id"]]["inicio"] == "2026-11-23"

    # Arrastar a barra fixa o "não iniciar antes de"; tirar devolve ao cálculo.
    c = cliente.patch(f"{url}/atividades/{ep['id']}", json={"inicio_fixo": "2026-12-01"}, headers=admin).json()
    assert {a["id"]: a for a in c["atividades"]}[ep["id"]]["inicio"] == "2026-12-01"
    c = cliente.patch(f"{url}/atividades/{ep['id']}", json={"inicio_fixo": None}, headers=admin).json()
    assert {a["id"]: a for a in c["atividades"]}[ep["id"]]["inicio"] == "2026-11-23"

    # Nova atividade logo abaixo, com predecessora TT.
    c = cliente.post(f"{url}/atividades", json={"fase": ep["fase"], "nome": "Visita ao terreno", "duracao": 2,
                                               "depois_de": ep["id"]}, headers=admin).json()
    nova = next(a for a in c["atividades"] if a["nome"] == "Visita ao terreno")
    assert nova["numero"] == por[ep["id"]]["numero"] + 1
    r = cliente.put(f"{url}/atividades/{nova['id']}/predecessoras",
                    json=[{"predecessora_id": ep["id"], "tipo": "tt", "defasagem": 0}], headers=admin)
    assert r.status_code == 200, r.text
    feita = next(a for a in r.json()["atividades"] if a["id"] == nova["id"])
    ep_agora = next(a for a in r.json()["atividades"] if a["id"] == ep["id"])
    assert feita["termino"] == ep_agora["termino"] and feita["predecessoras"][0]["tipo"] == "TT"

    # Ciclo é recusado.
    r = cliente.put(f"{url}/atividades/{topo['id']}/predecessoras", json=[{"predecessora_id": nova["id"]}], headers=admin)
    assert r.status_code == 422 and "ciclo" in r.text

    # Apagar a atividade leva os vínculos em que ela era predecessora.
    c = cliente.delete(f"{url}/atividades/{ep['id']}", headers=admin).json()
    assert all(p["predecessora_id"] != ep["id"] for a in c["atividades"] for p in a["predecessoras"])

    # Renomear fase e reordenar.
    c = cliente.patch(f"{url}/fases", json={"de": "PCP", "para": "Planejamento (PCP)"}, headers=admin).json()
    assert any(a["fase"] == "Planejamento (PCP)" for a in c["atividades"]) and all(a["fase"] != "PCP" for a in c["atividades"])
    ids = [a["id"] for a in c["atividades"]]
    c = cliente.put(f"{url}/ordem", json={"ids": ids[1:] + ids[:1]}, headers=admin).json()
    assert c["atividades"][-1]["id"] == ids[0]
    assert cliente.put(f"{url}/ordem", json={"ids": ids[1:]}, headers=admin).status_code == 422


def test_quem_acessa(cliente, admin, obra):
    coord = _pessoa(cliente, admin, obra, "coordcrn", "coordenador")
    proj = _pessoa(cliente, admin, obra, "projcrn", "projetista")
    gente_da_obra = _pessoa(cliente, admin, obra, "obracrn", "obra")
    url = f"/obras/{obra['id']}/cronograma"
    assert cliente.get(url, headers=coord).status_code == 200
    assert any(o["id"] == obra["id"] and o["tem_cronograma"] for o in cliente.get("/cronogramas", headers=coord).json())
    for quem in (proj, gente_da_obra):
        assert cliente.get(url, headers=quem).status_code == 403
        assert cliente.patch(url, json={"inicio": "2026-12-01"}, headers=quem).status_code == 403
        assert all(o["id"] != obra["id"] for o in cliente.get("/cronogramas", headers=quem).json())


def test_recomecar_em_branco(cliente, admin, obra):
    url = f"/obras/{obra['id']}/cronograma"
    assert cliente.delete(url, headers=admin).status_code == 204
    c = cliente.post(url, json={"inicio": "2026-11-02", "modelo": False}, headers=admin).json()
    assert c["existe"] and c["atividades"] == []
    c = cliente.post(f"{url}/atividades", json={"fase": "Projetos", "nome": "Primeira"}, headers=admin).json()
    assert c["atividades"][0]["inicio"] == "2026-11-02" and c["atividades"][0]["termino"] == "2026-11-06"
