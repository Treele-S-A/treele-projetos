"""Disciplina Incêndio (INC), no lugar do PCI da proposta inicial (05/10/2026)."""

import pytest

from app.db import SessionLocal
from app.models import Disciplina
from app.seed import semear

from .conftest import enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": "INC", "nome": "Obra incêndio"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def test_inc_esta_no_catalogo(cliente, admin):
    ativas = {d["codigo"]: d for d in cliente.get("/disciplinas", headers=admin).json()}
    assert ativas["INC"]["nome"] == "Incêndio"
    assert "PCI" not in ativas


def test_envio_com_inc(cliente, admin, obra):
    r = enviar_arquivo(cliente, admin, obra["id"], "INC-INC-PE-001-R00.pdf", PDF)
    assert r.status_code == 200, r.text


def test_pci_que_ja_existia_e_desativado_sem_ser_apagado():
    """Instalação em uso: o PCI cadastrado antes sai de circulação na subida."""
    with SessionLocal() as db:
        if db.query(Disciplina).filter_by(codigo="PCI").one_or_none() is None:
            db.add(Disciplina(codigo="PCI", nome="Prevenção e Combate a Incêndio", ordem=13))
            db.commit()
        semear(db)
        db.commit()
        pci = db.query(Disciplina).filter_by(codigo="PCI").one()
        assert pci.ativa is False
        assert db.query(Disciplina).filter_by(codigo="INC").one().ativa is True


def test_pci_desativado_nao_aceita_envio(cliente, admin, obra):
    r = enviar_arquivo(cliente, admin, obra["id"], "INC-PCI-PE-001-R00.pdf", PDF)
    assert r.status_code >= 400
    inativas = {d["codigo"]: d for d in cliente.get("/disciplinas?incluir_inativas=true", headers=admin).json()}
    assert inativas["PCI"]["ativa"] is False


def test_disciplinas_da_migracao_existem_separadas(cliente, admin):
    """CTL, LUM e SPD são disciplinas próprias, não pranchas de ARQ ou ELE
    (TREELE, 15/10/2026)."""
    codigos = {d["codigo"]: d for d in cliente.get("/disciplinas", headers=admin).json()}
    for codigo in ("CTL", "LUM", "SPD"):
        assert codigo in codigos, codigo
        assert codigos[codigo]["ativa"] is True
