"""Entrada pela Microsoft (Entra ID) respeita a caixa "Manter conectado por 30
dias" (TREELE, 26/11/2026): antes, a sessão era sempre a curta. A Microsoft é
simulada: o id_token é assinado aqui com uma chave RSA de teste."""

import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.api import auth
from app.config import settings
from app.security import ler_token

TENANT, CLIENTE = "tenant-teste", "cliente-teste"
CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def microsoft(monkeypatch):
    monkeypatch.setattr(settings, "entra_tenant_id", TENANT)
    monkeypatch.setattr(settings, "entra_client_id", CLIENTE)
    monkeypatch.setattr(settings, "entra_client_secret", "segredo-teste")
    nonce = {}

    class Resposta:
        def raise_for_status(self):
            pass

        def json(self):
            agora = int(time.time())
            return {"id_token": jwt.encode({
                "aud": CLIENTE, "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "tid": TENANT,
                "oid": "oid-teste", "nonce": nonce["valor"], "iat": agora, "exp": agora + 600,
                "email": "fulano.entra@treele.com.br", "name": "Fulano Entra",
            }, CHAVE, algorithm="RS256")}

    class Http:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return Resposta()

    class Chaves:
        def __init__(self, *a, **k):
            pass

        def get_signing_key_from_jwt(self, _):
            return type("Chave", (), {"key": CHAVE.public_key()})()

    monkeypatch.setattr(auth.httpx, "Client", Http)
    monkeypatch.setattr(auth.jwt, "PyJWKClient", Chaves)
    return nonce


def _entrar(cliente, nonce, manter):
    inicio = cliente.get("/auth/microsoft/start" + ("?manter=1" if manter else ""), follow_redirects=False)
    assert inicio.status_code in (302, 307), inicio.text
    consulta = parse_qs(urlsplit(inicio.headers["location"]).query)
    nonce["valor"] = consulta["nonce"][0]
    volta = cliente.get("/auth/microsoft/callback", params={"code": "codigo", "state": consulta["state"][0]},
                        follow_redirects=False)
    assert volta.status_code == 303
    destino = volta.headers["location"]
    assert "#entra_token=" in destino, destino
    return ler_token(destino.split("#entra_token=", 1)[1])


def _dias(payload):
    return (datetime.fromtimestamp(payload["exp"], timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 86400


def test_manter_conectado_vale_na_microsoft(cliente, microsoft):
    longo = _entrar(cliente, microsoft, manter=True)
    assert longo["lembrar"] is True and _dias(longo) > 29
    curto = _entrar(cliente, microsoft, manter=False)
    assert curto["lembrar"] is False and _dias(curto) < 1
