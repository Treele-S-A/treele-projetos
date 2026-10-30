"""Tipo de acesso editável e o usuário "todas as obras" (TREELE, 30/10/2026)."""

import pytest

from .conftest import EMAIL_ADMIN, autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
SENHA = "senha-acesso-1234"
END = "Rua de Teste, 100 – Curitiba – PR"


@pytest.fixture(scope="module")
def obras(cliente, admin):
    saida = []
    for c in ("TA1", "TA2"):
        r = cliente.post("/obras", json={"codigo": c, "nome": f"Obra {c}", "endereco": END}, headers=admin)
        assert r.status_code == 201, r.text
        saida.append(r.json())
    return saida


def _criar(cliente, admin, apelido, **extra):
    r = cliente.post(
        "/usuarios",
        json={"nome": apelido.title(), "email": f"{apelido}@ta.teste.com.br", "senha": SENHA, **extra},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_sem_senha_entra_so_pela_microsoft(cliente, admin):
    r = cliente.post("/usuarios", json={"nome": "Sem Senha", "email": "semsenha@ta.teste.com.br",
                                        "tipo": "todas_obras"}, headers=admin)
    assert r.status_code == 201, r.text
    assert r.json()["tipo"] == "todas_obras"
    # A senha local é uma que ninguém sabe: o login por senha não abre.
    assert cliente.post("/auth/login", json={"email": "semsenha@ta.teste.com.br", "senha": "qualquer-coisa"}).status_code == 401


def test_todas_as_obras_ve_toda_obra_como_equipe_de_campo(cliente, admin, obras):
    u = _criar(cliente, admin, "todasta", tipo="todas_obras")
    cab = autenticar(cliente, u["email"], SENHA)
    lista = {o["codigo"]: o for o in cliente.get("/obras", headers=cab).json()}
    assert {"TA1", "TA2"} <= set(lista) and lista["TA1"]["papel"] == "obra"
    # Obra criada depois também entra.
    nova = cliente.post("/obras", json={"codigo": "TA3", "nome": "Obra TA3", "endereco": END}, headers=admin).json()
    assert "TA3" in {o["codigo"] for o in cliente.get("/obras", headers=cab).json()}
    # Papel "obra": não envia arquivo.
    r = enviar_arquivo(cliente, cab, nova["id"], "TA3-ARQ-PE-001-R00.pdf", PDF)
    assert r.status_code == 403


def test_obra_especifica_e_troca_de_tipo(cliente, admin, obras):
    u = _criar(cliente, admin, "especta", tipo="obra_especifica", obras=[obras[0]["id"]])
    assert [o["codigo"] for o in u["obras"]] == ["TA1"] and u["obras"][0]["papel"] == "obra"
    cab = autenticar(cliente, u["email"], SENHA)
    assert [o["codigo"] for o in cliente.get("/obras", headers=cab).json()] == ["TA1"]

    r = cliente.patch(f"/usuarios/{u['id']}/acesso", json={"tipo": "obra_especifica", "obras": [obras[1]["id"]]}, headers=admin)
    assert [o["codigo"] for o in r.json()["obras"]] == ["TA2"]
    r = cliente.patch(f"/usuarios/{u['id']}/acesso", json={"tipo": "comercial"}, headers=admin)
    assert r.json()["tipo"] == "comercial" and r.json()["obras"] == []

    # Administrador rebaixado deixa de ser coordenador das obras.
    r = cliente.patch(f"/usuarios/{u['id']}/acesso", json={"tipo": "administrador"}, headers=admin)
    assert r.json()["tipo"] == "administrador" and all(o["papel"] == "coordenador" for o in r.json()["obras"])
    r = cliente.patch(f"/usuarios/{u['id']}/acesso", json={"tipo": "todas_obras"}, headers=admin)
    assert r.json()["tipo"] == "todas_obras" and r.json()["obras"] == []


def test_nao_tira_o_proprio_admin(cliente, admin):
    eu = next(u for u in cliente.get("/usuarios", headers=admin).json() if u["email"] == EMAIL_ADMIN)
    r = cliente.patch(f"/usuarios/{eu['id']}/acesso", json={"tipo": "todas_obras"}, headers=admin)
    assert r.status_code == 400
