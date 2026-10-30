"""Acesso de quem é de fora da Treèle (TREELE, 30/10/2026): login barrado com
o convite para pedir acesso, pedido público, aviso aos administradores,
aprovação (com a função ajustada) e o projetista só nas obras e disciplinas
dele. E os módulos Configurações e Qualidade só para administradores."""

import pytest

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
END = "Rua de Teste, 100 – Curitiba – PR"
SENHA = "senha-externa-123"


@pytest.fixture(scope="module")
def obras(cliente, admin):
    saida = {}
    for c in ("EXA", "EXB"):
        r = cliente.post("/obras", json={"codigo": c, "nome": f"Obra {c}", "endereco": END}, headers=admin)
        assert r.status_code == 201, r.text
        saida[c] = r.json()
    # Uma prancha de HID e uma de ELE na EXA, já liberadas.
    for disc in ("HID", "ELE"):
        r = enviar_arquivo(cliente, admin, saida["EXA"]["id"], f"EXA-{disc}-PE-001-R00.pdf", PDF)
        assert r.status_code == 200, r.text
        assert cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={}, headers=admin).status_code == 200
    return saida


def test_login_de_fora_sem_conta_pede_acesso(cliente):
    r = cliente.post("/auth/login", json={"email": "alguem@escritorio.com.br", "senha": "qualquer123"})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "sem_acesso"
    assert "Solicite seu acesso" in r.json()["detail"]["mensagem"]


def test_pedido_validacoes(cliente, obras):
    op = cliente.get("/acesso/opcoes").json()  # público
    assert {"EXA", "EXB"} <= {o["codigo"] for o in op["obras"]} and "COM" not in {d["codigo"] for d in op["disciplinas"]}
    base = {"nome": "Fulano de Tal", "email": "fulano@escritorio.com.br", "senha": SENHA}
    r = cliente.post("/acesso/solicitacoes", json={**base, "email": "x@treele.com.br", "funcao": "comercial"})
    assert r.status_code == 422 and "Microsoft" in r.text
    r = cliente.post("/acesso/solicitacoes", json={**base, "funcao": "projetista"})
    assert r.status_code == 422  # projetista sem obra e disciplina
    # Robô (campo escondido preenchido): finge que deu certo e não grava.
    assert cliente.post("/acesso/solicitacoes", json={**base, "funcao": "comercial", "site": "x"}).status_code == 201


def test_pedido_aprovado_projetista_so_ve_o_dele(cliente, admin, obras):
    r = cliente.post("/acesso/solicitacoes", json={
        "nome": "Paula Projetista", "email": "paula@hidroprojetos.com.br", "empresa": "Hidro Projetos",
        "funcao": "projetista", "obras": [obras["EXA"]["id"], obras["EXB"]["id"]],
        "disciplinas": ["HID", "ELE"], "senha": SENHA,
    })
    assert r.status_code == 201, r.text
    # De novo, o mesmo e-mail: já tem pedido aguardando.
    assert cliente.post("/acesso/solicitacoes", json={
        "nome": "Paula Projetista", "email": "paula@hidroprojetos.com.br", "funcao": "comercial", "senha": SENHA,
    }).status_code == 409
    # Os administradores foram avisados.
    avisos = cliente.get("/notificacoes", headers=admin).json()
    assert any(a["tipo"] == "solicitacao_acesso" and "Paula" in a["titulo"] for a in avisos)
    assert cliente.get("/acesso/solicitacoes/pendentes", headers=admin).json()["pendentes"] >= 1

    pedido = next(s for s in cliente.get("/acesso/solicitacoes?situacao=pendente", headers=admin).json()
                  if s["email"] == "paula@hidroprojetos.com.br")
    # O administrador ajusta: só a EXA, só HID.
    r = cliente.post(f"/acesso/solicitacoes/{pedido['id']}/aprovar",
                     json={"funcao": "projetista", "obras": [obras["EXA"]["id"]], "disciplinas": ["HID"]}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "aprovada", r.text

    paula = autenticar(cliente, "paula@hidroprojetos.com.br", SENHA)
    assert [o["codigo"] for o in cliente.get("/obras", headers=paula).json()] == ["EXA"]
    docs = cliente.get(f"/obras/{obras['EXA']['id']}/documentos", headers=paula).json()["itens"]
    assert [d["codigo"] for d in docs] == ["EXA-HID-PE-001"]
    # Envia na disciplina dela; na outra, não.
    assert enviar_arquivo(cliente, paula, obras["EXA"]["id"], "EXA-HID-PE-002-R00.pdf", PDF).status_code == 200
    assert enviar_arquivo(cliente, paula, obras["EXA"]["id"], "EXA-ELE-PE-002-R00.pdf", PDF).status_code == 403
    # Qualidade: sem fornecedores; atas, só das revisões em que está envolvida.
    assert cliente.get("/fornecedores", headers=paula).status_code == 403
    assert cliente.get("/atas", headers=paula).json()["itens"] == []


def test_pedido_reprovado_e_so_admin_decide(cliente, admin, obras):
    cliente.post("/acesso/solicitacoes", json={
        "nome": "Carlos Comercial", "email": "carlos@imobiliaria.com.br", "funcao": "comercial", "senha": SENHA,
    })
    pedido = next(s for s in cliente.get("/acesso/solicitacoes", headers=admin).json() if s["email"] == "carlos@imobiliaria.com.br")
    paula = autenticar(cliente, "paula@hidroprojetos.com.br", SENHA)
    assert cliente.get("/acesso/solicitacoes", headers=paula).status_code == 403
    r = cliente.post(f"/acesso/solicitacoes/{pedido['id']}/reprovar", json={"motivo": "Sem contrato vigente."}, headers=admin)
    assert r.json()["status"] == "reprovada"
    r = cliente.post("/auth/login", json={"email": "carlos@imobiliaria.com.br", "senha": SENHA})
    assert r.status_code == 403


def test_configuracoes_so_do_administrador(cliente, admin, obras):
    r = cliente.post("/usuarios", json={"nome": "Coord Ext", "email": "coordext@cfg.teste.com.br",
                                        "senha": SENHA, "tipo": "obra_especifica"}, headers=admin)
    uid = r.json()["id"]
    cliente.post(f"/obras/{obras['EXB']['id']}/membros", json={"usuario_id": uid, "papel": "coordenador"}, headers=admin)
    coord = autenticar(cliente, "coordext@cfg.teste.com.br", SENHA)
    assert cliente.patch(f"/obras/{obras['EXB']['id']}", json={"endereco": "Outra rua, 1"}, headers=coord).status_code == 403
    assert cliente.patch(f"/obras/{obras['EXB']['id']}", json={"endereco": "Outra rua, 1"}, headers=admin).status_code == 200
