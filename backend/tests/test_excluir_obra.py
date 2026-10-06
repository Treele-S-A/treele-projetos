"""Exclusão de obra — só administrador, com código digitado e senha (06/10/2026)."""

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Arquivo, Documento, Evento, Obra
from app.services.storage import armazenamento

from .conftest import SENHA_ADMIN, autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200


def _obra(cliente, admin, codigo):
    r = cliente.post("/obras", json={"codigo": codigo, "nome": f"Obra {codigo}"}, headers=admin)
    assert r.status_code == 201, r.text
    obra = r.json()
    r0 = enviar_arquivo(cliente, admin, obra["id"], f"{codigo}-ARQ-PE-001-R00.pdf", PDF)
    cliente.post(f"/revisoes/{r0.json()['revisao']['id']}/publicar", json={}, headers=admin)
    enviar_arquivo(cliente, admin, obra["id"], f"{codigo}-HID-PE-001-R00.pdf", PDF)
    return obra


@pytest.fixture(scope="module")
def coordenador(cliente, admin):
    r = cliente.post(
        "/usuarios",
        json={"nome": "Coord Exc", "email": "coord@exc.teste.com.br", "senha": "senha-exc-12345"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"], autenticar(cliente, "coord@exc.teste.com.br", "senha-exc-12345")


def _excluir(cliente, cab, obra, confirmacao=None, senha=SENHA_ADMIN):
    return cliente.post(
        f"/obras/{obra['id']}/excluir",
        json={"confirmacao": obra["codigo"] if confirmacao is None else confirmacao, "senha": senha},
        headers=cab,
    )


def _existe(obra_id):
    with SessionLocal() as db:
        return db.get(Obra, obra_id) is not None


def test_coordenador_nao_exclui(cliente, admin, coordenador):
    obra = _obra(cliente, admin, "EXA")
    usuario_id, cab = coordenador
    cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": usuario_id, "papel": "coordenador"}, headers=admin,
    )
    assert cliente.get(f"/obras/{obra['id']}/exclusao", headers=cab).status_code == 403
    assert _excluir(cliente, cab, obra, senha="senha-exc-12345").status_code == 403
    assert _existe(obra["id"])


def test_codigo_errado_nao_exclui(cliente, admin):
    obra = _obra(cliente, admin, "EXB")
    r = _excluir(cliente, admin, obra, confirmacao="EXA")
    assert r.status_code == 422
    assert "EXB" in r.json()["detail"]
    assert _existe(obra["id"])


def test_senha_errada_nao_exclui(cliente, admin):
    obra = _obra(cliente, admin, "EXC")
    r = _excluir(cliente, admin, obra, senha="nao-e-a-senha")
    assert r.status_code == 403
    assert "Senha incorreta" in r.json()["detail"]
    assert _existe(obra["id"])


def test_previa_conta_o_que_vai_junto(cliente, admin):
    obra = _obra(cliente, admin, "EXD")
    p = cliente.get(f"/obras/{obra['id']}/exclusao", headers=admin).json()
    assert p["codigo"] == "EXD"
    assert p["documentos"] == 2
    assert p["revisoes"] == 2
    assert p["arquivos"] == 2
    assert p["tamanho"] == 2 * len(PDF)


def test_exclui_a_obra_e_tudo_dela_e_guarda_o_registro(cliente, admin):
    outra = _obra(cliente, admin, "EXF")
    obra = _obra(cliente, admin, "EXE")
    doc = cliente.get(f"/obras/{obra['id']}/documentos?busca=EXE-ARQ", headers=admin).json()["itens"][0]
    pedido = cliente.post(
        f"/documentos/{doc['id']}/solicitacoes",
        json={"descricao": "Revisão para testar a exclusão da obra."}, headers=admin,
    )
    assert pedido.status_code == 201, pedido.text
    assert cliente.put(f"/obras/{obra['id']}/logo", content=PNG, headers=admin).status_code == 200
    with SessionLocal() as db:
        chaves = list(db.scalars(
            select(Arquivo.storage_key).join(Arquivo.revisao).join(Documento)
            .where(Documento.obra_id == obra["id"])
        ))
        logo = db.get(Obra, obra["id"]).logo_chave
    assert all(armazenamento.info(c)[0] for c in chaves + [logo])

    r = _excluir(cliente, admin, obra, confirmacao="exe")  # sem diferença de maiúscula
    assert r.status_code == 200, r.text
    assert r.json()["documentos"] == 2

    assert not _existe(obra["id"])
    assert cliente.get(f"/obras/{obra['id']}", headers=admin).status_code == 404
    assert cliente.get(f"/documentos/{doc['id']}", headers=admin).status_code == 404
    assert not any(armazenamento.info(c)[0] for c in chaves + [logo])
    # A outra obra fica intacta.
    assert _existe(outra["id"])
    assert cliente.get(f"/obras/{outra['id']}/documentos", headers=admin).json()["total"] == 2

    with SessionLocal() as db:
        ultimo = db.scalars(
            select(Evento).where(Evento.acao == "obra_excluida").order_by(Evento.id.desc())
        ).first()
        assert ultimo.detalhes["codigo"] == "EXE"
        assert ultimo.obra_id is None
        # O registro de antes continua lá — só sem a ligação com a obra.
        criada = db.scalars(
            select(Evento).where(Evento.acao == "obra_criada", Evento.entidade_id == obra["id"])
        ).first()
        assert criada is not None and criada.obra_id is None
