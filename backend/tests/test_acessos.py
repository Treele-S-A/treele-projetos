"""Controle de acessos (TREELE, 10/11/2026): cada entrada no sistema fica
registrada, e o coordenador acompanha a equipe das obras dele."""

from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Evento
from app.services.auditoria import dispositivo

from .conftest import autenticar

SENHA = "senha-acessos-12345"
CASA = "Rua de Teste, 100 – Centro – Curitiba – PR"
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def _pessoa(cliente, admin, apelido, obra=None, papel=None, comercial=False):
    email = f"{apelido}@acessos.teste.com.br"
    corpo = {"nome": apelido.title(), "email": email, "senha": SENHA}
    if comercial:
        corpo["tipo"] = "comercial"
    u = cliente.post("/usuarios", json=corpo, headers=admin)
    assert u.status_code == 201, u.text
    if obra:
        r = cliente.post(f"/obras/{obra}/membros", json={"usuario_id": u.json()["id"], "papel": papel}, headers=admin)
        assert r.status_code in (200, 201), r.text
    return u.json()["id"]


def _eventos(usuario_id):
    with SessionLocal() as db:
        return list(db.scalars(select(Evento).where(Evento.usuario_id == usuario_id, Evento.acao.in_(("login", "acesso")))
                               .order_by(Evento.id)))


def _envelhecer(usuario_id, minutos):
    with SessionLocal() as db:
        for e in db.scalars(select(Evento).where(Evento.usuario_id == usuario_id)):
            e.criado_em = e.criado_em - timedelta(minutes=minutos)
        db.commit()


def test_login_e_volta_com_sessao_aberta_ficam_registrados(cliente, admin):
    uid = _pessoa(cliente, admin, "volta")
    r = cliente.post("/auth/login", json={"email": "volta@acessos.teste.com.br", "senha": SENHA}, headers={"User-Agent": CHROME})
    cab = {"Authorization": f"Bearer {r.json()['token']}", "User-Agent": CHROME}
    ev = _eventos(uid)
    assert [e.acao for e in ev] == ["login"]
    assert ev[0].detalhes["metodo"] == "senha" and ev[0].detalhes["dispositivo"] == "Chrome no Windows"

    # Logo depois do login, abrir o sistema não conta de novo.
    assert cliente.post("/auth/acesso", headers=cab).status_code == 204
    assert len(_eventos(uid)) == 1
    # Passada meia hora, a mesma sessão (sem login) volta a contar.
    _envelhecer(uid, 31)
    assert cliente.post("/auth/acesso", headers=cab).status_code == 204
    ev = _eventos(uid)
    assert [e.acao for e in ev] == ["login", "acesso"] and ev[1].detalhes["dispositivo"] == "Chrome no Windows"
    assert cliente.post("/auth/acesso", headers=cab).status_code == 204
    assert len(_eventos(uid)) == 2


def test_coordenador_ve_a_equipe_das_obras_dele(cliente, admin):
    o1 = cliente.post("/obras", json={"codigo": "ACS1", "nome": "Obra acessos 1", "endereco": CASA}, headers=admin).json()["id"]
    o2 = cliente.post("/obras", json={"codigo": "ACS2", "nome": "Obra acessos 2", "endereco": CASA}, headers=admin).json()["id"]
    _pessoa(cliente, admin, "coordacs", o1, "coordenador")
    campo = _pessoa(cliente, admin, "campoacs", o1, "obra")
    longe = _pessoa(cliente, admin, "longeacs", o2, "obra")
    com = _pessoa(cliente, admin, "comacs", comercial=True)
    for apelido in ("campoacs", "longeacs", "comacs"):
        autenticar(cliente, f"{apelido}@acessos.teste.com.br", SENHA)
    coord = autenticar(cliente, "coordacs@acessos.teste.com.br", SENHA)

    r = cliente.get("/acessos", headers=coord)
    assert r.status_code == 200, r.text
    ids = {p["usuario"]["id"] for p in r.json()["pessoas"]}
    assert campo in ids and longe not in ids and com not in ids
    linhas = [i for i in r.json()["itens"] if i["usuario"]["id"] == campo]
    assert linhas and linhas[0]["tipo"] == "login_senha"
    assert cliente.get(f"/acessos?usuario_id={longe}", headers=coord).status_code == 404
    filtrado = cliente.get(f"/acessos?usuario_id={campo}", headers=coord).json()
    assert filtrado["total"] >= 1 and {i["usuario"]["id"] for i in filtrado["itens"]} == {campo}

    todos = cliente.get("/acessos?dias=3650", headers=admin).json()
    ids = {p["usuario"]["id"] for p in todos["pessoas"]}
    assert {campo, longe, com} <= ids


def test_quem_nao_coordena_nao_ve_o_controle(cliente, admin):
    o = cliente.post("/obras", json={"codigo": "ACS3", "nome": "Obra acessos 3", "endereco": CASA}, headers=admin).json()["id"]
    _pessoa(cliente, admin, "obraacs", o, "obra")
    _pessoa(cliente, admin, "projacs", o, "projetista")
    for apelido in ("obraacs", "projacs"):
        cab = autenticar(cliente, f"{apelido}@acessos.teste.com.br", SENHA)
        assert cliente.get("/acessos", headers=cab).status_code == 403


def test_dispositivo_legivel():
    class R:
        def __init__(self, ua):
            self.headers = {"user-agent": ua}

    assert dispositivo(R(CHROME)) == "Chrome no Windows"
    assert dispositivo(R("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")) == "Safari no iPhone"
    assert dispositivo(R("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/130.0 Safari/537.36 Edg/130.0")) == "Edge no Windows"
    assert dispositivo(R("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36")) == "Chrome no Android"
    assert dispositivo(R("")) is None
