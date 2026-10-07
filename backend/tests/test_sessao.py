"""Manter conectado (07/10/2026): sessão de 30 dias quando a pessoa pede, e
toda troca de senha derruba as sessões abertas."""

import uuid
from datetime import datetime, timezone

import jwt

from app.config import settings

SENHA = "senha-sessao-123"


def _usuario(cliente, admin):
    email = f"sessao-{uuid.uuid4().hex[:8]}@teste.com.br"
    r = cliente.post("/usuarios", json={"nome": "Sessão", "email": email, "senha": SENHA}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()["id"], email


def _login(cliente, email, manter=None):
    corpo = {"email": email, "senha": SENHA}
    if manter is not None:
        corpo["manter_conectado"] = manter
    r = cliente.post("/auth/login", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _dias_de_validade(token):
    exp = jwt.decode(token, settings.secret_key, algorithms=["HS256"])["exp"]
    return (datetime.fromtimestamp(exp, timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 86400


def test_sem_marcar_vale_12_horas(cliente, admin):
    _, email = _usuario(cliente, admin)
    r = _login(cliente, email)
    assert r["expira_em_minutos"] == 12 * 60
    assert 0.45 < _dias_de_validade(r["token"]) < 0.55


def test_manter_conectado_vale_30_dias(cliente, admin):
    _, email = _usuario(cliente, admin)
    r = _login(cliente, email, manter=True)
    assert r["expira_em_minutos"] == 30 * 24 * 60
    assert 29.9 < _dias_de_validade(r["token"]) <= 30


def test_redefinicao_pelo_administrador_derruba_as_sessoes(cliente, admin):
    uid, email = _usuario(cliente, admin)
    longa = {"Authorization": f"Bearer {_login(cliente, email, manter=True)['token']}"}
    assert cliente.get("/auth/eu", headers=longa).status_code == 200

    r = cliente.post(f"/usuarios/{uid}/senha", json={"senha_nova": "redefinida-123"}, headers=admin)
    assert r.status_code == 204, r.text

    caiu = cliente.get("/auth/eu", headers=longa)
    assert caiu.status_code == 401
    assert "senha mudou" in caiu.json()["detail"]


def test_troca_da_propria_senha_mantem_a_escolha(cliente, admin):
    _, email = _usuario(cliente, admin)
    longa = {"Authorization": f"Bearer {_login(cliente, email, manter=True)['token']}"}
    r = cliente.post(
        "/auth/senha", json={"senha_atual": SENHA, "senha_nova": "outra-senha-123"}, headers=longa,
    )
    assert r.status_code == 200, r.text
    assert r.json()["expira_em_minutos"] == 30 * 24 * 60


def test_token_sem_marca_da_senha_nao_vale(cliente, admin):
    """Token de antes desta regra, ou montado à mão: não entra."""
    uid, _ = _usuario(cliente, admin)
    antigo = jwt.encode(
        {"sub": str(uid), "exp": datetime.now(timezone.utc).timestamp() + 3600},
        settings.secret_key, algorithm="HS256",
    )
    assert cliente.get("/auth/eu", headers={"Authorization": f"Bearer {antigo}"}).status_code == 401
