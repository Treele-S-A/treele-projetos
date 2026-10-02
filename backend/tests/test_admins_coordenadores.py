"""Todo administrador é coordenador de todas as obras — as de hoje e as futuras,
e vale também para os administradores que forem criados depois."""

from app.db import SessionLocal
from app.models import Obra, ObraMembro, Usuario
from app.services.equipe import garantir_admins_coordenadores


def _papel(cliente, admin, obra_id, usuario_id):
    membros = cliente.get(f"/obras/{obra_id}/membros", headers=admin).json()
    return next((m["papel"] for m in membros if m["usuario_id"] == usuario_id), None)


def _admin_novo(cliente, admin, apelido):
    r = cliente.post(
        "/usuarios",
        json={
            "nome": apelido.title(), "email": f"{apelido}@adm.teste.com.br",
            "senha": "senha-admin-novo1", "admin": True,
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_obra_nova_tem_todos_os_admins_como_coordenadores(cliente, admin):
    outro = _admin_novo(cliente, admin, "admin-antes-da-obra")
    obra = cliente.post("/obras", json={"codigo": "ADM1", "nome": "Obra adm"}, headers=admin).json()

    eu = cliente.get("/auth/eu", headers=admin).json()["id"]
    assert _papel(cliente, admin, obra["id"], eu) == "coordenador"
    assert _papel(cliente, admin, obra["id"], outro) == "coordenador"


def test_admin_novo_vira_coordenador_das_obras_que_ja_existem(cliente, admin):
    obra = cliente.post("/obras", json={"codigo": "ADM2", "nome": "Obra adm 2"}, headers=admin).json()
    novo = _admin_novo(cliente, admin, "admin-depois-da-obra")
    assert _papel(cliente, admin, obra["id"], novo) == "coordenador"
    # E aparece como coordenador para ele mesmo, na lista de obras.
    lista = cliente.post(
        "/auth/login",
        json={"email": "admin-depois-da-obra@adm.teste.com.br", "senha": "senha-admin-novo1"},
    ).json()["token"]
    obras = cliente.get("/obras", headers={"Authorization": f"Bearer {lista}"}).json()
    assert next(o for o in obras if o["codigo"] == "ADM2")["papel"] == "coordenador"


def test_admin_nao_sai_da_equipe_nem_troca_de_papel(cliente, admin):
    obra = cliente.post("/obras", json={"codigo": "ADM3", "nome": "Obra adm 3"}, headers=admin).json()
    eu = cliente.get("/auth/eu", headers=admin).json()["id"]
    membros = cliente.get(f"/obras/{obra['id']}/membros", headers=admin).json()
    meu = next(m for m in membros if m["usuario_id"] == eu)

    assert cliente.delete(f"/obras/{obra['id']}/membros/{meu['id']}", headers=admin).status_code == 400
    r = cliente.post(
        f"/obras/{obra['id']}/membros", json={"usuario_id": eu, "papel": "obra"}, headers=admin
    )
    assert r.status_code == 409
    assert _papel(cliente, admin, obra["id"], eu) == "coordenador"


def test_subida_corrige_o_que_ja_existia(cliente, admin):
    """O que existia antes da regra (admin fora da equipe, ou com outro papel)
    é corrigido na subida do sistema, que chama esta mesma função."""
    obra = cliente.post("/obras", json={"codigo": "ADM4", "nome": "Obra adm 4"}, headers=admin).json()
    eu = cliente.get("/auth/eu", headers=admin).json()["id"]
    with SessionLocal() as db:
        membro = db.query(ObraMembro).filter_by(obra_id=obra["id"], usuario_id=eu).one()
        db.delete(membro)
        db.commit()
        assert garantir_admins_coordenadores(db) >= 1
        db.commit()
    assert _papel(cliente, admin, obra["id"], eu) == "coordenador"


def test_comercial_nunca_entra(cliente, admin):
    cliente.post(
        "/usuarios",
        json={
            "nome": "Com", "email": "com-adm@teste.com.br", "senha": "senha-comercial-9",
            "comercial": True,
        },
        headers=admin,
    )
    with SessionLocal() as db:
        com = db.query(Usuario).filter_by(email="com-adm@teste.com.br").one()
        garantir_admins_coordenadores(db)
        db.commit()
        assert db.query(ObraMembro).filter_by(usuario_id=com.id).count() == 0
        assert db.query(Obra).count() > 0
