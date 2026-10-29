"""Fornecedores de projetos — PRO-FL-002 (TREELE, 29/10/2026): cadastro,
qualificação documental como na planilha e avaliação de desempenho (5.3)."""

import pytest

from .conftest import autenticar

SENHA = "senha-forn-12345"


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post(
        "/obras", json={"codigo": "FRN", "nome": "Obra fornecedores", "endereco": "Rua A, 1 – Curitiba – PR"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _pessoa(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@frn.teste.com.br"
    r = cliente.post("/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA}, headers=admin)
    assert r.status_code == 201, r.text
    if papel:
        m = cliente.post(f"/obras/{obra['id']}/membros", json={"usuario_id": r.json()["id"], "papel": papel}, headers=admin)
        assert m.status_code in (200, 201), m.text
    return autenticar(cliente, email, SENHA)


CODICE = {
    "cod_sienge": "4490", "razao_social": "CODICE ENGENHARIA LTDA", "nome_fantasia": "CODICE ENGENHARIA LTDA",
    "cnpj": "56.971.388/0001-22", "contato": "Fulano", "email": "contato@exemplo.com.br",
    "registro_conselho": "SIM", "portfolio": True, "escopos": ["ELE", "HID", "GAS", "XYZ"], "padroes": ["MCMV"],
}


def test_cadastro_e_qualificacao_documental(cliente, admin):
    r = cliente.post("/fornecedores", json=CODICE, headers=admin)
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["escopos"] == ["ELE", "HID", "GAS"]  # o que não existe sai
    assert f["qualificacao"] == "qualificado" and f["situacao"] == "qualificado" and not f["avaliado"]

    sem_portfolio = {**CODICE, "razao_social": "SEM PORTFOLIO LTDA", "portfolio": False}
    assert cliente.post("/fornecedores", json=sem_portfolio, headers=admin).json()["qualificacao"] == "desqualificado"
    pendente = {"razao_social": "BAEPRO ENGENHARIA E PROJETOS LTDA", "escopos": ["EST", "FUN"]}
    p = cliente.post("/fornecedores", json=pendente, headers=admin).json()
    assert p["qualificacao"] is None and p["situacao"] == "pendente"


def test_avaliacao_de_desempenho(cliente, admin, obra):
    f = next(x for x in cliente.get("/fornecedores", headers=admin).json() if x["cod_sienge"] == "4490")
    base = {"obra_id": obra["id"], "escopo": "ELE", "data": "2026-10-20T12:00:00Z"}
    r = cliente.post(f"/fornecedores/{f['id']}/avaliacoes",
                     json={**base, "qualidade": 9, "documentacao": 8, "prazo": 7, "atendimento": 10}, headers=admin)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["ultima_avaliacao"]["media"] == 8.5 and d["continua_qualificado"] is True
    assert d["ultima_avaliacao"]["empreendimento"] == "FRN · Obra fornecedores"

    # Abaixo de 6: desqualifica, e o motivo é obrigatório.
    ruim = {**base, "data": "2026-10-28T12:00:00Z", "qualidade": 5, "documentacao": 4, "prazo": 3, "atendimento": 6}
    r = cliente.post(f"/fornecedores/{f['id']}/avaliacoes", json=ruim, headers=admin)
    assert r.status_code == 422 and "motivo" in r.text
    r = cliente.post(f"/fornecedores/{f['id']}/avaliacoes", json={**ruim, "motivo": "Atrasou duas entregas."}, headers=admin)
    d = r.json()
    assert d["situacao"] == "desqualificado" and d["ultima_avaliacao"]["motivo"] == "Atrasou duas entregas."
    assert d["total_avaliacoes"] == 2 and d["media_geral"] == pytest.approx((8.5 + 4.5) / 2)
    assert [a["media"] for a in d["avaliacoes"]] == [4.5, 8.5]  # a mais recente primeiro


def test_quem_ve_fornecedores(cliente, admin, obra):
    coord = _pessoa(cliente, admin, obra, "coordfrn", "coordenador")
    proj = _pessoa(cliente, admin, obra, "projfrn", "projetista")
    assert cliente.get("/fornecedores", headers=coord).status_code == 200
    assert cliente.get("/fornecedores", headers=proj).status_code == 403
