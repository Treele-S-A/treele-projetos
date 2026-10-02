"""Notificações (TREELE, 02/10/2026).

Pedido de revisão: coordenadores sempre, projetista só se subiu a última
revisão. Revisão liberada: só o papel "obra", uma vez por revisão. Fica no
sistema e vai por e-mail quando configurado.
"""

import pytest

from app.config import settings

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
DWG = b"AC1032" + b"\x00" * 200
PEDIDO = "Mudar a posição do ralo do banheiro social."
SENHA = "senha-ntf-12345"


def _usuario(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@ntf.teste.com.br"
    r = cliente.post(
        "/usuarios", json={"nome": f"{apelido.title()} Silva", "email": email, "senha": SENHA},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    if papel:
        m = cliente.post(
            f"/obras/{obra['id']}/membros",
            json={"usuario_id": r.json()["id"], "papel": papel},
            headers=admin,
        )
        assert m.status_code in (200, 201), m.text
    return autenticar(cliente, email, SENHA)


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": "NTF", "nome": "Obra avisos"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def p(cliente, admin, obra):
    return {
        "campo": _usuario(cliente, admin, obra, "campo", "obra"),
        "campo2": _usuario(cliente, admin, obra, "campodois", "obra"),
        "autor": _usuario(cliente, admin, obra, "autor", "projetista"),
        "outro": _usuario(cliente, admin, obra, "outro", "projetista"),
        "coord": _usuario(cliente, admin, obra, "coord", "coordenador"),
        "fora": _usuario(cliente, admin, obra, "fora", None),
    }


def _avisos(cliente, cab):
    r = cliente.get("/notificacoes", headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def _limpar(cliente, *cabs):
    for cab in cabs:
        assert cliente.post("/notificacoes/lidas", headers=cab).status_code == 204


def _nao_lidas(cliente, cab):
    return cliente.get("/notificacoes/contagem", headers=cab).json()["nao_lidas"]


def _liberar(cliente, admin, obra, envia, prancha, rev="00", extras=()):
    r = enviar_arquivo(cliente, envia, obra["id"], f"NTF-ARQ-PE-{prancha}-R{rev}.pdf", PDF)
    assert r.status_code == 200, r.text
    for nome, conteudo in extras:
        e = enviar_arquivo(cliente, envia, obra["id"], f"NTF-ARQ-PE-{prancha}-R{rev}.{nome}", conteudo)
        assert e.status_code == 200, e.text
    revisao_id = r.json()["revisao"]["id"]
    pub = cliente.post(f"/revisoes/{revisao_id}/publicar", json={}, headers=admin)
    assert pub.status_code == 200, pub.text
    doc = cliente.get(f"/obras/{obra['id']}/documentos?busca=NTF-ARQ-PE-{prancha}", headers=admin)
    return doc.json()["itens"][0]["id"]


def test_pedido_avisa_coordenadores_e_quem_subiu_a_ultima(cliente, admin, obra, p):
    doc = _liberar(cliente, admin, obra, p["autor"], "001")
    _limpar(cliente, admin, *p.values())

    r = cliente.post(f"/documentos/{doc}/solicitacoes", json={"descricao": PEDIDO}, headers=p["campo"])
    assert r.status_code == 201, r.text

    for quem in ("coord", "autor"):
        avisos = _avisos(cliente, p[quem])
        assert avisos[0]["tipo"] == "solicitacao_revisao"
        assert avisos[0]["documento_id"] == doc
        assert avisos[0]["obra_codigo"] == "NTF"
        assert "Campo Silva pediu revisão da R00" in avisos[0]["texto"]
        assert PEDIDO in avisos[0]["texto"]
        assert _nao_lidas(cliente, p[quem]) == 1
    # Administrador é coordenador de todas as obras: recebe também.
    assert _nao_lidas(cliente, admin) == 1
    # Projetista que não subiu a última revisão, quem pediu, outra pessoa da
    # obra e quem é de fora: nada.
    for quem in ("outro", "campo", "campo2", "fora"):
        assert _nao_lidas(cliente, p[quem]) == 0, quem


def test_projetista_da_revisao_em_andamento_e_quem_recebe(cliente, admin, obra, p):
    """Já tem R01 subindo pela mão de outro projetista: é ele quem precisa saber."""
    doc = _liberar(cliente, admin, obra, p["autor"], "002")
    r = enviar_arquivo(cliente, p["outro"], obra["id"], "NTF-ARQ-PE-002-R01.pdf", PDF)
    assert r.status_code == 200, r.text
    _limpar(cliente, admin, *p.values())

    cliente.post(f"/documentos/{doc}/solicitacoes", json={"descricao": PEDIDO}, headers=p["campo"])
    assert _nao_lidas(cliente, p["outro"]) == 1
    assert _nao_lidas(cliente, p["autor"]) == 0


def test_coordenador_que_pede_nao_avisa_a_si_mesmo(cliente, admin, obra, p):
    doc = _liberar(cliente, admin, obra, p["autor"], "003")
    _limpar(cliente, admin, *p.values())

    cliente.post(f"/documentos/{doc}/solicitacoes", json={"descricao": PEDIDO}, headers=p["coord"])
    assert _nao_lidas(cliente, p["coord"]) == 0
    assert _nao_lidas(cliente, admin) == 1
    assert _nao_lidas(cliente, p["autor"]) == 1


def test_liberacao_avisa_so_a_obra_uma_vez_por_revisao(cliente, admin, obra, p):
    _limpar(cliente, admin, *p.values())
    _liberar(cliente, admin, obra, p["autor"], "004", extras=[("dwg", DWG)])

    for quem in ("campo", "campo2"):
        avisos = [a for a in _avisos(cliente, p[quem]) if not a["lida"]]
        assert len(avisos) == 1, quem
        assert avisos[0]["tipo"] == "revisao_liberada"
        assert avisos[0]["titulo"] == "R00 liberada para obra · NTF-ARQ-PE-004"
        assert "Emissão para teste" in avisos[0]["texto"]
        # Primeira revisão: não há anterior para descartar.
        assert "deixa de valer" not in avisos[0]["texto"]
    for quem in ("autor", "outro", "coord", "fora"):
        assert _nao_lidas(cliente, p[quem]) == 0, quem
    assert _nao_lidas(cliente, admin) == 0


def test_liberacao_de_revisao_nova_diz_qual_deixa_de_valer(cliente, admin, obra, p):
    _liberar(cliente, admin, obra, p["autor"], "009")
    _limpar(cliente, p["campo"])
    _liberar(cliente, admin, obra, p["autor"], "009", rev="01")
    aviso = _avisos(cliente, p["campo"])[0]
    assert aviso["titulo"] == "R01 liberada para obra · NTF-ARQ-PE-009"
    assert "A R00 deixa de valer" in aviso["texto"]


def test_envio_sem_liberar_nao_avisa_a_obra(cliente, admin, obra, p):
    _limpar(cliente, *p.values())
    r = enviar_arquivo(cliente, p["autor"], obra["id"], "NTF-ARQ-PE-005-R00.pdf", PDF)
    assert r.status_code == 200, r.text
    assert _nao_lidas(cliente, p["campo"]) == 0


def test_marcar_como_lida(cliente, admin, obra, p):
    doc = _liberar(cliente, admin, obra, p["autor"], "006")
    _limpar(cliente, admin, *p.values())
    cliente.post(f"/documentos/{doc}/solicitacoes", json={"descricao": PEDIDO}, headers=p["campo"])
    aviso = _avisos(cliente, p["coord"])[0]

    # De outra pessoa: como se não existisse.
    assert cliente.post(f"/notificacoes/{aviso['id']}/lida", headers=p["autor"]).status_code == 404
    assert _nao_lidas(cliente, p["coord"]) == 1

    assert cliente.post(f"/notificacoes/{aviso['id']}/lida", headers=p["coord"]).status_code == 204
    assert _nao_lidas(cliente, p["coord"]) == 0
    assert _avisos(cliente, p["coord"])[0]["lida"] is True
    # A do projetista continua não lida: cada um marca a sua.
    assert _nao_lidas(cliente, p["autor"]) == 1


def test_exige_login(cliente):
    assert cliente.get("/notificacoes/contagem").status_code == 401


class _SmtpFalso:
    enviados: list = []
    falhar_conexao = False

    def __init__(self, host, porta, timeout=None):
        if _SmtpFalso.falhar_conexao:
            raise OSError("sem rede")

    def starttls(self, context=None):
        pass

    def login(self, usuario, senha):
        pass

    def send_message(self, msg):
        _SmtpFalso.enviados.append(msg)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def smtp(monkeypatch):
    import app.services.email as modulo

    monkeypatch.setattr(settings, "email_smtp_host", "smtp.exemplo.com")
    monkeypatch.setattr(settings, "email_smtp_usuario", "usuario")
    monkeypatch.setattr(settings, "email_smtp_senha", "senha")
    monkeypatch.setattr(settings, "email_remetente", "Treèle Projetos <projetos@treele.com.br>")
    monkeypatch.setattr(modulo.smtplib, "SMTP", _SmtpFalso)
    _SmtpFalso.enviados = []
    _SmtpFalso.falhar_conexao = False
    return _SmtpFalso


def test_email_vai_para_cada_destinatario_com_o_link(cliente, admin, obra, p, smtp):
    doc = _liberar(cliente, admin, obra, p["autor"], "007")
    smtp.enviados = []

    r = cliente.post(f"/documentos/{doc}/solicitacoes", json={"descricao": PEDIDO}, headers=p["campo"])
    assert r.status_code == 201, r.text

    para = {m["To"] for m in smtp.enviados}
    assert {"coord@ntf.teste.com.br", "autor@ntf.teste.com.br", "admin@teste.com.br"} <= para
    assert "campo@ntf.teste.com.br" not in para
    assert "outro@ntf.teste.com.br" not in para
    msg = next(m for m in smtp.enviados if m["To"] == "coord@ntf.teste.com.br")
    assert msg["Subject"] == "[NTF] Revisão solicitada · NTF-ARQ-PE-007"
    corpo = msg.get_content()
    assert "Olá, Coord." in corpo
    assert PEDIDO in corpo
    assert f"http://testserver/documentos/{doc}" in corpo


def test_email_que_falha_nao_derruba_o_pedido(cliente, admin, obra, p, smtp):
    doc = _liberar(cliente, admin, obra, p["autor"], "008")
    _limpar(cliente, p["coord"])
    smtp.falhar_conexao = True

    r = cliente.post(f"/documentos/{doc}/solicitacoes", json={"descricao": PEDIDO}, headers=p["campo"])
    assert r.status_code == 201, r.text
    # O aviso no sistema vale do mesmo jeito.
    assert _nao_lidas(cliente, p["coord"]) == 1


def test_endereco_do_site_tira_o_prefixo_da_api(monkeypatch):
    monkeypatch.setattr(settings, "base_url", "https://projetos.treele.com.br/api")
    monkeypatch.setattr(settings, "api_prefix", "/api")
    assert settings.endereco_site == "https://projetos.treele.com.br"


def test_email_de_teste_so_para_administrador(cliente, admin, p, smtp):
    assert cliente.post("/notificacoes/email-teste", headers=p["coord"]).status_code == 403
    r = cliente.post("/notificacoes/email-teste", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["enviado"] is True
    assert [m["To"] for m in smtp.enviados] == ["admin@teste.com.br"]


def test_email_de_teste_explica_a_senha_recusada(cliente, admin, smtp, monkeypatch):
    import smtplib

    def recusa(self, usuario, senha):
        raise smtplib.SMTPAuthenticationError(535, b"Authentication failed")

    monkeypatch.setattr(smtp, "login", recusa)
    r = cliente.post("/notificacoes/email-teste", headers=admin).json()
    assert r["enviado"] is False
    assert "API key" in r["erro"]


def test_email_de_teste_explica_dominio_nao_verificado(cliente, admin, smtp, monkeypatch):
    import smtplib

    def recusa(self, msg):
        raise smtplib.SMTPSenderRefused(550, b"The treele.com.br domain is not verified", "x")

    monkeypatch.setattr(smtp, "send_message", recusa)
    r = cliente.post("/notificacoes/email-teste", headers=admin).json()
    assert r["enviado"] is False
    assert "verificado no Resend" in r["erro"]
    assert "not verified" in r["erro"]


def test_email_de_teste_explica_dominio_recusado_na_entrega(cliente, admin, smtp, monkeypatch):
    """Caso real: o Resend recusa no DATA, não no remetente."""
    import smtplib

    def recusa(self, msg):
        raise smtplib.SMTPDataError(550, b"The treele.com.br domain is not verified.")

    monkeypatch.setattr(smtp, "send_message", recusa)
    r = cliente.post("/notificacoes/email-teste", headers=admin).json()
    assert "ainda não está verificado no Resend" in r["erro"]


def test_email_de_teste_com_email_desligado(cliente, admin):
    r = cliente.post("/notificacoes/email-teste", headers=admin).json()
    assert r["enviado"] is False
    assert "EMAIL_SMTP_HOST" in r["erro"]
