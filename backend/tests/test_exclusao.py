"""Nada se exclui: revisões e obras ficam (TREELE, 09/10/2026).

Controle de documentos auditado (PBQP-H) guarda o histórico. Revisão que não
vale é CANCELADA — continua no histórico dizendo que não vale. O coordenador
cancela a que está em revisão; o administrador, qualquer uma, a qualquer
tempo. A obra nunca fica sem revisão válida por causa de um cancelamento.

Arquivo avulso o administrador ainda exclui, mas só de revisão em revisão
(14/10/2026): é a saída para o arquivo que entrou trocado durante a análise.
Depois dela, o arquivo é histórico.
"""

import pytest

from app.services.storage import armazenamento, montar_chave

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
OBRA = "EXC001"


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": OBRA, "nome": "Obra de exclusão", "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def coordenador(cliente, admin, obra):
    """Coordenador cancela o que está em revisão — e só isso."""
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


# ------------------------------------------------------------ nada se exclui


def test_revisao_nao_se_exclui_nem_pelo_administrador(cliente, admin, obra):
    _, revisao, _ = _enviar(cliente, admin, obra, "001", "00", liberar=True)

    assert cliente.delete(f"/revisoes/{revisao['id']}", headers=admin).status_code == 405
    assert cliente.get(f"/revisoes/{revisao['id']}", headers=admin).status_code == 200


def test_obra_nao_se_exclui_nem_pelo_administrador(cliente, admin, obra):
    corpo = {"confirmacao": OBRA, "senha": "qualquer"}
    assert cliente.post(f"/obras/{obra['id']}/excluir", json=corpo, headers=admin).status_code in (404, 405)
    assert cliente.get(f"/obras/{obra['id']}/exclusao", headers=admin).status_code in (404, 405)
    assert cliente.delete(f"/obras/{obra['id']}", headers=admin).status_code in (404, 405)
    assert cliente.get(f"/obras/{obra['id']}", headers=admin).status_code == 200


# ------------------------------------------------------------ arquivos


def test_admin_exclui_arquivo_de_revisao_em_revisao(cliente, admin, obra):
    arquivo, revisao, nome = _enviar(cliente, admin, obra, "002", "00")
    assert _no_armazenamento("002", "00", nome)

    r = cliente.delete(f"/arquivos/{arquivo['id']}", headers=admin)

    assert r.status_code == 204, r.text
    restante = cliente.get(f"/revisoes/{revisao['id']}", headers=admin).json()
    assert restante["arquivos"] == []
    assert not _no_armazenamento("002", "00", nome)

    evento = _ultimo_evento(cliente, admin, obra)
    assert evento["acao"] == "arquivo_removido"
    assert evento["detalhes"]["arquivo"] == nome
    assert evento["detalhes"]["situacao_revisao"] == "em_revisao"


def test_arquivo_de_revisao_ja_analisada_nao_se_exclui(cliente, admin, obra):
    """Liberada, reprovada, obsoleta ou cancelada: o arquivo é histórico."""
    arquivo, revisao, nome = _enviar(cliente, admin, obra, "008", "00", liberar=True)

    r = cliente.delete(f"/arquivos/{arquivo['id']}", headers=admin)

    assert r.status_code == 409
    assert "cancele" in r.json()["detail"]
    assert len(cliente.get(f"/revisoes/{revisao['id']}", headers=admin).json()["arquivos"]) == 1
    assert _no_armazenamento("008", "00", nome)

    cancelada, rc, _ = _enviar(cliente, admin, obra, "009", "00")
    assert cliente.post(f"/revisoes/{rc['id']}/cancelar", headers=admin).status_code == 200
    assert cliente.delete(f"/arquivos/{cancelada['id']}", headers=admin).status_code == 409


# ------------------------------------------------------------ cancelar


def test_coordenador_cancela_so_o_que_esta_em_revisao(cliente, admin, coordenador, obra):
    _, liberada, _ = _enviar(cliente, admin, obra, "003", "00", liberar=True)
    r = cliente.post(f"/revisoes/{liberada['id']}/cancelar", headers=coordenador)
    assert r.status_code == 403
    assert "administrador" in r.json()["detail"]

    _, andamento, _ = _enviar(cliente, admin, obra, "004", "00")
    r = cliente.post(f"/revisoes/{andamento['id']}/cancelar", headers=coordenador)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelado"


def test_admin_cancela_a_liberada_e_a_anterior_volta_a_valer(cliente, admin, obra):
    """Sem isto, cancelar a R01 errada deixaria a obra sem nenhuma revisão
    válida do documento — a R00 continuaria marcada como obsoleta."""
    _, r00, _ = _enviar(cliente, admin, obra, "005", "00", liberar=True)
    _, r01, nome01 = _enviar(cliente, admin, obra, "005", "01", liberar=True)
    assert cliente.get(f"/revisoes/{r00['id']}", headers=admin).json()["status"] == "obsoleto"

    r = cliente.post(f"/revisoes/{r01['id']}/cancelar", headers=admin)

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelado"
    volta = cliente.get(f"/revisoes/{r00['id']}", headers=admin).json()
    assert volta["status"] == "liberado_para_obra"
    assert volta["obsoleta_em"] is None
    # A cancelada fica no histórico, com os arquivos.
    cancelada = cliente.get(f"/revisoes/{r01['id']}", headers=admin).json()
    assert [a["nome_original"] for a in cancelada["arquivos"]] == [nome01]
    assert _no_armazenamento("005", "01", nome01)

    doc = _documento(cliente, admin, obra, f"{OBRA}-ARQ-EP-005")
    assert doc["revisao_atual"]["numero"] == "00"
    assert doc["revisao_atual"]["status"] == "liberado_para_obra"

    evento = _ultimo_evento(cliente, admin, obra)
    assert evento["acao"] == "revisao_cancelada"
    assert evento["detalhes"]["situacao_revisao"] == "liberado_para_obra"
    assert evento["detalhes"]["restaurada"] == "00"


def test_admin_cancela_a_obsoleta_sem_mexer_na_liberada(cliente, admin, obra):
    _, r00, _ = _enviar(cliente, admin, obra, "006", "00", liberar=True)
    _, r01, _ = _enviar(cliente, admin, obra, "006", "01", liberar=True)

    r = cliente.post(f"/revisoes/{r00['id']}/cancelar", headers=admin)

    assert r.status_code == 200, r.text
    assert cliente.get(f"/revisoes/{r01['id']}", headers=admin).json()["status"] == "liberado_para_obra"


def test_cancelar_duas_vezes_avisa(cliente, admin, obra):
    _, r00, _ = _enviar(cliente, admin, obra, "007", "00")
    assert cliente.post(f"/revisoes/{r00['id']}/cancelar", headers=admin).status_code == 200
    r = cliente.post(f"/revisoes/{r00['id']}/cancelar", headers=admin)
    assert r.status_code == 409
