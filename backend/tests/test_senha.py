"""Troca de senha pela própria pessoa e redefinição pelo administrador.

Cada teste cria o próprio usuário: o administrador da sessão de testes é
compartilhado, e trocar a senha dele quebraria o resto da suíte.
"""

import uuid

from .conftest import autenticar


def _novo_usuario(cliente, admin, senha="senha-inicial-123") -> tuple[int, str]:
    email = f"pessoa-{uuid.uuid4().hex[:8]}@treele.com.br"
    r = cliente.post(
        "/usuarios",
        json={"nome": "Pessoa de teste", "email": email, "senha": senha, "admin": False},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"], email


def _entra(cliente, email, senha) -> bool:
    return cliente.post("/auth/login", json={"email": email, "senha": senha}).status_code == 200


# ------------------------------------------------------- a própria pessoa


def test_pessoa_troca_a_propria_senha(cliente, admin):
    _, email = _novo_usuario(cliente, admin)
    eu = autenticar(cliente, email, "senha-inicial-123")

    r = cliente.post(
        "/auth/senha",
        json={"senha_atual": "senha-inicial-123", "senha_nova": "nova-senha-456"},
        headers=eu,
    )

    assert r.status_code == 204, r.text
    assert _entra(cliente, email, "nova-senha-456")
    assert not _entra(cliente, email, "senha-inicial-123")


def test_senha_atual_errada_nao_troca_nem_derruba_a_sessao(cliente, admin):
    """400, e não 401: a tela trata 401 como sessão expirada e deslogaria a
    pessoa só por ter errado a senha atual."""
    _, email = _novo_usuario(cliente, admin)
    eu = autenticar(cliente, email, "senha-inicial-123")

    r = cliente.post(
        "/auth/senha",
        json={"senha_atual": "chutada", "senha_nova": "nova-senha-456"},
        headers=eu,
    )

    assert r.status_code == 400
    assert "Senha atual incorreta" in r.json()["detail"]
    assert _entra(cliente, email, "senha-inicial-123")


def test_senha_nova_curta_e_recusada(cliente, admin):
    _, email = _novo_usuario(cliente, admin)
    eu = autenticar(cliente, email, "senha-inicial-123")

    r = cliente.post(
        "/auth/senha",
        json={"senha_atual": "senha-inicial-123", "senha_nova": "curta"},
        headers=eu,
    )

    assert r.status_code == 422
    assert _entra(cliente, email, "senha-inicial-123")


def test_trocar_senha_exige_login(cliente):
    r = cliente.post("/auth/senha", json={"senha_atual": "x", "senha_nova": "y" * 8})
    assert r.status_code == 401


# ------------------------------------------------------- o administrador


def test_admin_redefine_senha_pelo_corpo(cliente, admin):
    uid, email = _novo_usuario(cliente, admin)

    r = cliente.post(
        f"/usuarios/{uid}/senha", json={"senha_nova": "redefinida-789"}, headers=admin
    )

    assert r.status_code == 204, r.text
    assert _entra(cliente, email, "redefinida-789")
    assert not _entra(cliente, email, "senha-inicial-123")


def test_senha_na_url_nao_e_aceita(cliente, admin):
    """Endereço com query string vai inteiro para o log de acesso da
    hospedagem. A senha nunca pode viajar ali — nem por engano."""
    uid, email = _novo_usuario(cliente, admin)

    r = cliente.post(f"/usuarios/{uid}/senha?senha_nova=vazada-na-url", headers=admin)

    assert r.status_code == 422
    assert not _entra(cliente, email, "vazada-na-url")


def test_admin_nao_redefine_senha_curta(cliente, admin):
    uid, _ = _novo_usuario(cliente, admin)
    r = cliente.post(f"/usuarios/{uid}/senha", json={"senha_nova": "curta"}, headers=admin)
    assert r.status_code == 422


def test_so_admin_redefine_senha_alheia(cliente, admin):
    uid, email = _novo_usuario(cliente, admin)
    _, outro_email = _novo_usuario(cliente, admin)
    outro = autenticar(cliente, outro_email, "senha-inicial-123")

    r = cliente.post(
        f"/usuarios/{uid}/senha", json={"senha_nova": "tomada-de-conta"}, headers=outro
    )

    assert r.status_code == 403
    assert _entra(cliente, email, "senha-inicial-123")
