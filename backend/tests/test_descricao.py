"""O que mudou na revisão: dito por quem sobe o primeiro arquivo dela.

Antes era pedido na liberação, a quem libera. Agora é obrigatório no envio,
para quem abre a revisão — projetista ou coordenador (TREELE, 02/10/2026).
Os arquivos seguintes da mesma revisão não pedem de novo.
"""

import pytest

from .conftest import SEM_DESCRICAO, autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
DWG = b"AC1032" + b"\x00" * 200


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": "DSC", "nome": "Obra descrição"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def projetista(cliente, admin, obra):
    r = cliente.post(
        "/usuarios",
        json={"nome": "Proj", "email": "proj-dsc@teste.com.br", "senha": "senha-proj-dsc1"},
        headers=admin,
    )
    cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": r.json()["id"], "papel": "projetista"},
        headers=admin,
    )
    return autenticar(cliente, "proj-dsc@teste.com.br", "senha-proj-dsc1")


def test_revisao_nova_sem_descricao_e_recusada(cliente, projetista, obra):
    r = enviar_arquivo(
        cliente, projetista, obra["id"], "DSC-ARQ-PE-001-R00.pdf", PDF, descricao=SEM_DESCRICAO
    )
    assert r.status_code == 422
    assert "o que mudou" in r.text.lower()


def test_recusa_nao_deixa_rastro(cliente, admin, obra):
    """Conferido antes de criar o documento: nada sobra de um envio recusado."""
    enviar_arquivo(cliente, admin, obra["id"], "DSC-ARQ-PE-009-R00.pdf", PDF, descricao="  ")
    lista = cliente.get(f"/obras/{obra['id']}/documentos?busca=DSC-ARQ-PE-009", headers=admin)
    assert lista.json()["total"] == 0


def test_quem_sobe_o_primeiro_arquivo_descreve(cliente, admin, projetista, obra):
    r = enviar_arquivo(
        cliente, projetista, obra["id"], "DSC-ARQ-PE-002-R00.dwg", DWG,
        descricao="Emissão inicial da planta baixa.",
    )
    assert r.status_code == 200, r.text
    assert r.json()["revisao"]["descricao"] == "Emissão inicial da planta baixa."


def test_arquivo_seguinte_da_mesma_revisao_nao_pede(cliente, projetista, obra):
    enviar_arquivo(
        cliente, projetista, obra["id"], "DSC-ARQ-PE-003-R00.dwg", DWG, descricao="Primeira emissão."
    )
    r = enviar_arquivo(
        cliente, projetista, obra["id"], "DSC-ARQ-PE-003-R00.pdf", PDF, descricao=SEM_DESCRICAO
    )
    assert r.status_code == 200, r.text
    assert r.json()["revisao"]["descricao"] == "Primeira emissão."


def test_descricao_do_segundo_arquivo_nao_sobrescreve(cliente, projetista, obra):
    enviar_arquivo(
        cliente, projetista, obra["id"], "DSC-ARQ-PE-004-R00.dwg", DWG, descricao="A original."
    )
    r = enviar_arquivo(
        cliente, projetista, obra["id"], "DSC-ARQ-PE-004-R00.pdf", PDF, descricao="Outra coisa."
    )
    assert r.json()["revisao"]["descricao"] == "A original."


def test_cada_revisao_nova_pede_a_sua(cliente, admin, obra):
    """Vale para a R01, R02... — inclusive para o coordenador."""
    r00 = enviar_arquivo(cliente, admin, obra["id"], "DSC-ARQ-PE-005-R00.pdf", PDF)
    cliente.post(f"/revisoes/{r00.json()['revisao']['id']}/publicar", json={}, headers=admin)

    sem = enviar_arquivo(
        cliente, admin, obra["id"], "DSC-ARQ-PE-005-R01.pdf", PDF, descricao=SEM_DESCRICAO
    )
    assert sem.status_code == 422

    com = enviar_arquivo(
        cliente, admin, obra["id"], "DSC-ARQ-PE-005-R01.pdf", PDF,
        descricao="Ajuste das cotas do eixo 4.",
    )
    assert com.status_code == 200, com.text


def test_liberar_nao_pede_descricao(cliente, admin, obra):
    r = enviar_arquivo(cliente, admin, obra["id"], "DSC-ARQ-PE-006-R00.pdf", PDF)
    p = cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={}, headers=admin)
    assert p.status_code == 200, p.text
    assert p.json()["descricao"] == "Emissão para teste"


def test_tela_sabe_quando_vai_pedir(cliente, admin, obra):
    enviar_arquivo(cliente, admin, obra["id"], "DSC-ARQ-PE-007-R00.pdf", PDF)
    r = cliente.post(
        f"/obras/{obra['id']}/nomenclatura/validar",
        json={"nomes": ["DSC-ARQ-PE-007-R00.dwg", "DSC-ARQ-PE-007-R01.pdf", "DSC-ARQ-PE-008-R00.pdf"]},
        headers=admin,
    )
    pede = [x["precisa_descricao"] for x in r.json()["resultados"]]
    assert pede == [False, True, True]
