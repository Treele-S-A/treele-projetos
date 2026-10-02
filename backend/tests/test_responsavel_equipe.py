"""O engenheiro responsável inclui e remove pessoas da equipe da própria obra.

Não nomeia nem remove coordenador, não troca papel de quem já está e não tira
a si mesmo. E vale só para a obra de que ele é o responsável.
"""

import pytest

from .conftest import autenticar


def _usuario(cliente, admin, apelido):
    email = f"{apelido}@resp.teste.com.br"
    r = cliente.post(
        "/usuarios",
        json={"nome": apelido.title(), "email": email, "senha": "senha-resp-1234"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"], email


def _obra(cliente, admin, codigo):
    r = cliente.post("/obras", json={"codigo": codigo, "nome": f"Obra {codigo}"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def cenario(cliente, admin):
    obra = _obra(cliente, admin, "RSP")
    outra = _obra(cliente, admin, "RSQ")
    eng_id, eng_email = _usuario(cliente, admin, "engenheiro")
    # Responsável com papel "obra": o caso comum do engenheiro de campo.
    for o in (obra, outra):
        r = cliente.post(
            f"/obras/{o['id']}/membros",
            json={"usuario_id": eng_id, "papel": "obra"},
            headers=admin,
        )
        assert r.status_code == 201, r.text
    r = cliente.patch(f"/obras/{obra['id']}", json={"responsavel_id": eng_id}, headers=admin)
    assert r.status_code == 200, r.text
    return {
        "obra": obra,
        "outra": outra,
        "eng": autenticar(cliente, eng_email, "senha-resp-1234"),
    }


def _membros(cliente, admin, obra):
    return {
        m["usuario_id"]: m["papel"]
        for m in cliente.get(f"/obras/{obra['id']}/membros", headers=admin).json()
    }


def test_responsavel_inclui_pessoa_na_equipe(cliente, admin, cenario):
    novo, _ = _usuario(cliente, admin, "projetista-novo")

    r = cliente.post(
        f"/obras/{cenario['obra']['id']}/membros",
        json={"usuario_id": novo, "papel": "projetista"},
        headers=cenario["eng"],
    )

    assert r.status_code == 201, r.text
    assert _membros(cliente, admin, cenario["obra"])[novo] == "projetista"
    evento = cliente.get(f"/obras/{cenario['obra']['id']}/eventos", headers=admin).json()["itens"][0]
    assert evento["acao"] == "membro_adicionado"


def test_a_tela_sabe_que_ele_pode_incluir(cliente, cenario):
    obra = cliente.get(f"/obras/{cenario['obra']['id']}", headers=cenario["eng"]).json()
    assert "adicionar_membro" in obra["permissoes"]
    assert "remover_membro" in obra["permissoes"]
    assert "gerenciar" not in obra["permissoes"]
    outra = cliente.get(f"/obras/{cenario['outra']['id']}", headers=cenario["eng"]).json()
    assert "adicionar_membro" not in outra["permissoes"]


def test_responsavel_nao_nomeia_coordenador(cliente, admin, cenario):
    novo, _ = _usuario(cliente, admin, "quase-coordenador")
    r = cliente.post(
        f"/obras/{cenario['obra']['id']}/membros",
        json={"usuario_id": novo, "papel": "coordenador"},
        headers=cenario["eng"],
    )
    assert r.status_code == 403
    assert novo not in _membros(cliente, admin, cenario["obra"])


def test_responsavel_nao_troca_papel_de_quem_ja_esta(cliente, admin, cenario):
    novo, _ = _usuario(cliente, admin, "ja-na-equipe")
    obra = cenario["obra"]["id"]
    cliente.post(f"/obras/{obra}/membros", json={"usuario_id": novo, "papel": "obra"}, headers=admin)

    r = cliente.post(
        f"/obras/{obra}/membros",
        json={"usuario_id": novo, "papel": "projetista"},
        headers=cenario["eng"],
    )

    assert r.status_code == 409
    assert _membros(cliente, admin, cenario["obra"])[novo] == "obra"


def _id_do_membro(cliente, admin, obra, usuario_id):
    membros = cliente.get(f"/obras/{obra['id']}/membros", headers=admin).json()
    return next(m["id"] for m in membros if m["usuario_id"] == usuario_id)


def test_responsavel_remove_pessoa_da_equipe(cliente, admin, cenario):
    obra = cenario["obra"]
    novo, _ = _usuario(cliente, admin, "de-saida")
    cliente.post(
        f"/obras/{obra['id']}/membros", json={"usuario_id": novo, "papel": "obra"}, headers=admin
    )

    r = cliente.delete(
        f"/obras/{obra['id']}/membros/{_id_do_membro(cliente, admin, obra, novo)}",
        headers=cenario["eng"],
    )

    assert r.status_code == 204, r.text
    assert novo not in _membros(cliente, admin, obra)
    evento = cliente.get(f"/obras/{obra['id']}/eventos", headers=admin).json()["itens"][0]
    assert evento["acao"] == "membro_removido"
    assert evento["detalhes"]["usuario_id"] == novo


def test_responsavel_nao_remove_coordenador(cliente, admin, cenario):
    obra = cenario["obra"]
    coord, _ = _usuario(cliente, admin, "coordenador-comum")
    cliente.post(
        f"/obras/{obra['id']}/membros", json={"usuario_id": coord, "papel": "coordenador"},
        headers=admin,
    )
    r = cliente.delete(
        f"/obras/{obra['id']}/membros/{_id_do_membro(cliente, admin, obra, coord)}",
        headers=cenario["eng"],
    )
    assert r.status_code == 403


def test_responsavel_nao_tira_a_si_mesmo(cliente, admin, cenario):
    obra = cenario["obra"]
    eu = cliente.get("/auth/eu", headers=cenario["eng"]).json()
    r = cliente.delete(
        f"/obras/{obra['id']}/membros/{_id_do_membro(cliente, admin, obra, eu['id'])}",
        headers=cenario["eng"],
    )
    assert r.status_code == 400


def test_remover_o_responsavel_da_equipe_limpa_o_responsavel(cliente, admin):
    """Responsável precisa ser da equipe. Antes, removê-lo deixava a obra
    apontando para alguém de fora."""
    obra = _obra(cliente, admin, "RSZ")
    pessoa, _ = _usuario(cliente, admin, "responsavel-removido")
    cliente.post(
        f"/obras/{obra['id']}/membros", json={"usuario_id": pessoa, "papel": "obra"}, headers=admin
    )
    cliente.patch(f"/obras/{obra['id']}", json={"responsavel_id": pessoa}, headers=admin)

    r = cliente.delete(
        f"/obras/{obra['id']}/membros/{_id_do_membro(cliente, admin, obra, pessoa)}",
        headers=admin,
    )

    assert r.status_code == 204, r.text
    assert cliente.get(f"/obras/{obra['id']}", headers=admin).json()["responsavel"] is None


def test_responsavel_nao_mexe_na_equipe_de_outra_obra(cliente, admin, cenario):
    """Na outra obra ele é só "obra", sem ser o responsável."""
    novo, _ = _usuario(cliente, admin, "outra-obra")
    r = cliente.post(
        f"/obras/{cenario['outra']['id']}/membros",
        json={"usuario_id": novo, "papel": "obra"},
        headers=cenario["eng"],
    )
    assert r.status_code == 403


def test_responsavel_nao_ganha_o_resto_do_gerenciar(cliente, cenario):
    obra = cenario["obra"]["id"]
    eng = cenario["eng"]
    assert cliente.patch(f"/obras/{obra}", json={"nome": "Outro"}, headers=eng).status_code == 403
    assert cliente.get(f"/obras/{obra}/eventos", headers=eng).status_code == 403


def test_deixou_de_ser_responsavel_perde_a_permissao(cliente, admin, cenario):
    obra = cenario["obra"]
    cliente.patch(f"/obras/{obra['id']}", json={"responsavel_id": 0}, headers=admin)
    novo, _ = _usuario(cliente, admin, "depois-da-troca")

    r = cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": novo, "papel": "obra"},
        headers=cenario["eng"],
    )

    assert r.status_code == 403


def test_papel_cliente_nao_existe_mais(cliente, admin, cenario):
    """Saiu em 02/10/2026: a TREELE não usa esse papel."""
    novo, _ = _usuario(cliente, admin, "ex-cliente")
    r = cliente.post(
        f"/obras/{cenario['obra']['id']}/membros",
        json={"usuario_id": novo, "papel": "cliente"},
        headers=admin,
    )
    assert r.status_code == 422
