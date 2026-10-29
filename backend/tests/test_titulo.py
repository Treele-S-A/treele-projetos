"""Título obrigatório no primeiro envio do documento (TREELE, 25/09/2026).

Pedido na primeira vez que o documento aparece; das revisões seguintes em
diante, reaproveitado. A regra é do servidor — a tela só pergunta.
"""

import pytest

from app.db import SessionLocal
from app.models import Documento

from .conftest import SEM_TITULO, autorizar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
DWG = b"AC1032" + b"\x00" * 200


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post(
        "/obras", json={"codigo": "TIT001", "nome": "Residencial Título", "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"}, headers=admin
    )
    assert r.status_code == 201, r.text
    return r.json()


def _documento(cliente, admin, obra_id, codigo):
    r = cliente.get(
        f"/obras/{obra_id}/documentos", params={"busca": codigo}, headers=admin
    )
    itens = [d for d in r.json()["itens"] if d["codigo"] == codigo]
    return itens[0] if itens else None


def _validar(cliente, admin, obra_id, nome):
    r = cliente.post(
        f"/obras/{obra_id}/nomenclatura/validar", json={"nomes": [nome]}, headers=admin
    )
    assert r.status_code == 200, r.text
    return r.json()["resultados"][0]


# --------------------------------------------------------------------------


def test_documento_novo_sem_titulo_e_recusado_sem_deixar_rastro(cliente, admin, obra):
    r = enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-001-R00.pdf", PDF, titulo=SEM_TITULO
    )
    assert r.status_code == 422
    assert "título" in r.json()["detail"]["mensagem"]
    # Recusado antes de criar qualquer coisa.
    assert _documento(cliente, admin, obra["id"], "TIT001-ARQ-PE-001") is None


@pytest.mark.parametrize("titulo", ["", "   ", "ab", "x" * 301])
def test_titulo_vazio_curto_ou_longo_e_recusado(cliente, admin, obra, titulo):
    r = enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-002-R00.pdf", PDF, titulo=titulo
    )
    assert r.status_code == 422
    assert _documento(cliente, admin, obra["id"], "TIT001-ARQ-PE-002") is None


def test_documento_novo_com_titulo_nasce_com_ele(cliente, admin, obra):
    r = enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-003-R00.pdf", PDF,
        titulo="  Planta   Pav.  Térreo ",
    )
    assert r.status_code == 200, r.text
    # Espaços sobrando são limpos: o título tem a mesma cara em todo lugar.
    assert _documento(cliente, admin, obra["id"], "TIT001-ARQ-PE-003")["titulo"] == "Planta Pav. Térreo"


def test_revisoes_seguintes_aproveitam_o_titulo(cliente, admin, obra):
    r = enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-004-R00.pdf", PDF, titulo="Cortes AA e BB"
    )
    # Companheiro da mesma revisão e revisão nova: nenhum pede título.
    assert enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-004-R00.dwg", DWG, titulo=SEM_TITULO
    ).status_code == 200
    cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={}, headers=admin)
    autorizar(cliente, admin, obra["id"], "TIT001-ARQ-PE-004")
    assert enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-004-R01.pdf", PDF, titulo=SEM_TITULO
    ).status_code == 200
    assert _documento(cliente, admin, obra["id"], "TIT001-ARQ-PE-004")["titulo"] == "Cortes AA e BB"


def test_titulo_diferente_numa_revisao_seguinte_e_ignorado(cliente, admin, obra):
    """Título se troca na tela do documento, de propósito — não por acidente,
    no meio de um envio."""
    r = enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-005-R00.pdf", PDF, titulo="Fachada Norte"
    )
    cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={}, headers=admin)
    assert enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-005-R01.pdf", PDF, titulo="Outra coisa",
        autorizar_com=admin,
    ).status_code == 200
    assert _documento(cliente, admin, obra["id"], "TIT001-ARQ-PE-005")["titulo"] == "Fachada Norte"


def test_documento_antigo_sem_titulo_pede_um_no_proximo_envio(cliente, admin, obra):
    r = enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-006-R00.pdf", PDF, titulo="Provisório"
    )
    cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={}, headers=admin)
    autorizar(cliente, admin, obra["id"], "TIT001-ARQ-PE-006")
    # Simula um documento de antes da regra, que ficou sem título.
    with SessionLocal() as db:
        doc = db.query(Documento).filter_by(codigo="TIT001-ARQ-PE-006").one()
        doc.titulo = None
        db.commit()

    assert _validar(cliente, admin, obra["id"], "TIT001-ARQ-PE-006-R01.pdf")["precisa_titulo"]
    sem = enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-006-R01.pdf", PDF, titulo=SEM_TITULO
    )
    assert sem.status_code == 422

    com = enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-006-R01.pdf", PDF, titulo="Detalhe da Escada"
    )
    assert com.status_code == 200, com.text
    assert _documento(cliente, admin, obra["id"], "TIT001-ARQ-PE-006")["titulo"] == "Detalhe da Escada"


def test_conferencia_previa_avisa_quando_vai_pedir_titulo(cliente, admin, obra):
    novo = _validar(cliente, admin, obra["id"], "TIT001-ARQ-PE-007-R00.pdf")
    assert novo["precisa_titulo"] is True
    assert novo["documento_titulo"] is None

    enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-007-R00.pdf", PDF, titulo="Planta de Cobertura"
    )
    seguinte = _validar(cliente, admin, obra["id"], "TIT001-ARQ-PE-007-R01.pdf")
    assert seguinte["precisa_titulo"] is False
    # Quem manda a R01 vê de qual prancha se trata.
    assert seguinte["documento_titulo"] == "Planta de Cobertura"


def test_nome_fora_do_padrao_nao_pede_titulo(cliente, admin, obra):
    """Arquivo que não vai subir não precisa de título — pedir seria ruído."""
    r = _validar(cliente, admin, obra["id"], "qualquer-coisa.pdf")
    assert r["valido"] is False
    assert r["precisa_titulo"] is False


def test_titulo_nao_pode_ser_apagado_na_edicao(cliente, admin, obra):
    enviar_arquivo(
        cliente, admin, obra["id"], "TIT001-ARQ-PE-008-R00.pdf", PDF, titulo="Planta de Forro"
    )
    doc = _documento(cliente, admin, obra["id"], "TIT001-ARQ-PE-008")

    for vazio in ["", "   ", "ab"]:
        r = cliente.patch(f"/documentos/{doc['id']}", json={"titulo": vazio}, headers=admin)
        assert r.status_code == 422
    assert _documento(cliente, admin, obra["id"], "TIT001-ARQ-PE-008")["titulo"] == "Planta de Forro"

    r = cliente.patch(
        f"/documentos/{doc['id']}", json={"titulo": "Planta de Forro — Térreo"}, headers=admin
    )
    assert r.status_code == 200
    assert r.json()["titulo"] == "Planta de Forro — Térreo"
