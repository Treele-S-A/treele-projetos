"""Exclusão de arquivos e revisões — só administrador, em qualquer status.

É a saída para o que nunca deveria ter entrado (obra errada, arquivo trocado).
Por ser definitiva, as regras que importam são: ninguém além do administrador
exclui; a obra nunca fica sem revisão válida por causa de uma exclusão; e o
registro de atividades guarda o que saiu.
"""

import pytest

from app.services.storage import armazenamento, montar_chave

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
OBRA = "EXC001"


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": OBRA, "nome": "Obra de exclusão"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def coordenador(cliente, admin, obra):
    """Coordenador pode quase tudo na obra — menos excluir."""
    r = cliente.post(
        "/usuarios",
        json={"nome": "Coord", "email": "coord-exc@teste.com.br", "senha": "senha-coord-123"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    add = cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": r.json()["id"], "papel": "coordenador"},
        headers=admin,
    )
    assert add.status_code == 201, add.text
    return autenticar(cliente, "coord-exc@teste.com.br", "senha-coord-123")


def _enviar(cliente, admin, obra, prancha, rev, liberar=False):
    nome = f"{OBRA}-ARQ-EP-{prancha}-R{rev}.pdf"
    r = enviar_arquivo(cliente, admin, obra["id"], nome, PDF,
                       autorizar_com=admin if rev != "00" else None)
    assert r.status_code == 200, r.text
    corpo = r.json()
    if liberar:
        p = cliente.post(
            f"/revisoes/{corpo['revisao']['id']}/publicar", json={}, headers=admin
        )
        assert p.status_code == 200, p.text
    return corpo["arquivo"], corpo["revisao"], nome


def _documento(cliente, admin, obra, codigo):
    r = cliente.get(f"/obras/{obra['id']}/documentos", params={"busca": codigo}, headers=admin)
    return next((d for d in r.json()["itens"] if d["codigo"] == codigo), None)


def _no_armazenamento(prancha, rev, nome) -> bool:
    chave = montar_chave(OBRA, f"{OBRA}-ARQ-EP-{prancha}", rev, nome)
    return armazenamento.info(chave)[0]


def _ultimo_evento(cliente, admin, obra):
    return cliente.get(f"/obras/{obra['id']}/eventos", headers=admin).json()["itens"][0]


# ------------------------------------------------------------ quem exclui


def test_coordenador_nao_exclui_nem_em_andamento(cliente, admin, coordenador, obra):
    arquivo, revisao, _ = _enviar(cliente, admin, obra, "001", "00")

    assert cliente.delete(f"/arquivos/{arquivo['id']}", headers=coordenador).status_code == 403
    assert cliente.delete(f"/revisoes/{revisao['id']}", headers=coordenador).status_code == 403
    assert cliente.get(f"/revisoes/{revisao['id']}", headers=admin).status_code == 200


# ------------------------------------------------------------ arquivos


def test_admin_exclui_arquivo_de_revisao_liberada(cliente, admin, obra):
    arquivo, revisao, nome = _enviar(cliente, admin, obra, "002", "00", liberar=True)
    assert _no_armazenamento("002", "00", nome)

    r = cliente.delete(f"/arquivos/{arquivo['id']}", headers=admin)

    assert r.status_code == 204, r.text
    restante = cliente.get(f"/revisoes/{revisao['id']}", headers=admin).json()
    assert restante["arquivos"] == []
    assert not _no_armazenamento("002", "00", nome)

    evento = _ultimo_evento(cliente, admin, obra)
    assert evento["acao"] == "arquivo_removido"
    assert evento["detalhes"]["arquivo"] == nome
    assert evento["detalhes"]["situacao_revisao"] == "liberado_para_obra"


# ------------------------------------------------------------ revisões


def test_excluir_a_liberada_devolve_a_validade_a_anterior(cliente, admin, obra):
    """Sem isto, excluir a R01 errada deixaria a obra sem nenhuma revisão
    válida do documento — a R00 continuaria marcada como obsoleta."""
    _, r00, _ = _enviar(cliente, admin, obra, "003", "00", liberar=True)
    _, r01, nome01 = _enviar(cliente, admin, obra, "003", "01", liberar=True)
    assert cliente.get(f"/revisoes/{r00['id']}", headers=admin).json()["status"] == "obsoleto"

    r = cliente.delete(f"/revisoes/{r01['id']}", headers=admin)

    assert r.status_code == 200, r.text
    assert r.json() == {"restaurada": "00", "documento_excluido": False}
    assert cliente.get(f"/revisoes/{r01['id']}", headers=admin).status_code == 404
    volta = cliente.get(f"/revisoes/{r00['id']}", headers=admin).json()
    assert volta["status"] == "liberado_para_obra"
    assert volta["obsoleta_em"] is None
    assert not _no_armazenamento("003", "01", nome01)

    doc = _documento(cliente, admin, obra, f"{OBRA}-ARQ-EP-003")
    assert doc["revisao_atual"]["numero"] == "00"
    assert doc["revisao_atual"]["status"] == "liberado_para_obra"


def test_excluir_revisao_em_andamento_nao_mexe_na_liberada(cliente, admin, obra):
    _, r00, _ = _enviar(cliente, admin, obra, "004", "00", liberar=True)
    _, r01, _ = _enviar(cliente, admin, obra, "004", "01")

    r = cliente.delete(f"/revisoes/{r01['id']}", headers=admin)

    assert r.status_code == 200, r.text
    assert r.json() == {"restaurada": None, "documento_excluido": False}
    assert cliente.get(f"/revisoes/{r00['id']}", headers=admin).json()["status"] == "liberado_para_obra"


def test_excluir_a_unica_revisao_tira_o_documento_do_acervo(cliente, admin, obra):
    _, r00, nome = _enviar(cliente, admin, obra, "005", "00", liberar=True)
    codigo = f"{OBRA}-ARQ-EP-005"
    doc = _documento(cliente, admin, obra, codigo)

    r = cliente.delete(f"/revisoes/{r00['id']}", headers=admin)

    assert r.status_code == 200, r.text
    assert r.json() == {"restaurada": None, "documento_excluido": True}
    assert _documento(cliente, admin, obra, codigo) is None
    assert cliente.get(f"/documentos/{doc['id']}", headers=admin).status_code == 404
    assert not _no_armazenamento("005", "00", nome)


def test_exclusao_de_revisao_fica_no_registro(cliente, admin, obra):
    _, r00, nome = _enviar(cliente, admin, obra, "006", "00")
    cliente.delete(f"/revisoes/{r00['id']}", headers=admin)

    evento = _ultimo_evento(cliente, admin, obra)
    assert evento["acao"] == "revisao_excluida"
    assert evento["detalhes"]["documento"] == f"{OBRA}-ARQ-EP-006"
    assert evento["detalhes"]["revisao"] == "00"
    assert evento["detalhes"]["arquivos"] == [nome]
    assert evento["detalhes"]["documento_excluido"] is True


def test_documento_excluido_pode_ser_enviado_de_novo(cliente, admin, obra):
    """Excluir é para corrigir: o mesmo código precisa poder voltar limpo."""
    _, r00, _ = _enviar(cliente, admin, obra, "007", "00")
    cliente.delete(f"/revisoes/{r00['id']}", headers=admin)

    _, nova, _ = _enviar(cliente, admin, obra, "007", "00")
    assert nova["numero"] == "00"
