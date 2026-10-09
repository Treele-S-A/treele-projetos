"""Análise crítica da revisão (TREELE, 09/10/2026 — PBQP-H).

Revisão "em revisão" é a análise crítica: o coordenador libera para obra ou
reprova. A observação é opcional ao liberar e obrigatória ao reprovar. A
reprovada fica no histórico como registro da análise, quem a enviou recebe a
observação (sistema e e-mail), e a correção vem numa revisão nova — sem
precisar de outra autorização.
"""

import pytest

from app.config import settings

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
SENHA = "senha-anc-12345"
OBS = "Falta cotar a escada no corte AA e o nível do patamar."
OBRA = "ANC"


def _usuario(cliente, admin, obra, apelido, papel):
    email = f"{apelido}@anc.teste.com.br"
    r = cliente.post(
        "/usuarios", json={"nome": f"{apelido.title()} Souza", "email": email, "senha": SENHA},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    m = cliente.post(
        f"/obras/{obra['id']}/membros",
        json={"usuario_id": r.json()["id"], "papel": papel},
        headers=admin,
    )
    assert m.status_code in (200, 201), m.text
    return autenticar(cliente, email, SENHA)


@pytest.fixture(scope="module")
def obra(cliente, admin):
    r = cliente.post("/obras", json={"codigo": OBRA, "nome": "Obra análise"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def p(cliente, admin, obra):
    return {
        "coord": _usuario(cliente, admin, obra, "coordanc", "coordenador"),
        "proj": _usuario(cliente, admin, obra, "projanc", "projetista"),
        "outro": _usuario(cliente, admin, obra, "outroanc", "projetista"),
        "campo": _usuario(cliente, admin, obra, "campoanc", "obra"),
    }


def _enviar(cliente, cab, obra, prancha, rev="00", autorizar_com=None):
    r = enviar_arquivo(cliente, cab, obra["id"], f"{OBRA}-ARQ-PE-{prancha}-R{rev}.pdf", PDF,
                       autorizar_com=autorizar_com)
    assert r.status_code == 200, r.text
    return r.json()["revisao"]


def _reprovar(cliente, cab, revisao, observacao=OBS):
    return cliente.post(f"/revisoes/{revisao['id']}/reprovar", json={"observacao": observacao}, headers=cab)


def _avisos(cliente, cab):
    return [a for a in cliente.get("/notificacoes", headers=cab).json() if not a["lida"]]


def _limpar(cliente, *cabs):
    for cab in cabs:
        assert cliente.post("/notificacoes/lidas", headers=cab).status_code == 204


# ------------------------------------------------------------ reprovar


def test_reprovar_exige_observacao(cliente, p, obra):
    revisao = _enviar(cliente, p["proj"], obra, "001")

    assert _reprovar(cliente, p["coord"], revisao, "").status_code == 422
    r = _reprovar(cliente, p["coord"], revisao, "   ")
    assert r.status_code == 422
    assert "observação" in r.json()["detail"]
    assert cliente.get(f"/revisoes/{revisao['id']}", headers=p["coord"]).json()["status"] == "em_revisao"


def test_so_o_coordenador_reprova(cliente, p, obra):
    revisao = _enviar(cliente, p["proj"], obra, "002")
    assert _reprovar(cliente, p["proj"], revisao).status_code == 403


def test_reprovada_fica_no_historico_com_quem_quando_e_observacao(cliente, admin, p, obra):
    revisao = _enviar(cliente, p["proj"], obra, "003")

    r = _reprovar(cliente, p["coord"], revisao)

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "reprovado"
    assert corpo["observacao"] == OBS
    assert corpo["reprovada_por"]["nome"] == "Coordanc Souza"
    assert corpo["reprovada_em"]
    assert len(corpo["arquivos"]) == 1

    evento = cliente.get(f"/obras/{obra['id']}/eventos", headers=admin).json()["itens"][0]
    assert evento["acao"] == "revisao_reprovada"
    assert evento["detalhes"]["observacao"] == OBS
    assert evento["detalhes"]["revisao"] == "00"


def test_so_revisao_em_revisao_passa_pela_analise(cliente, p, obra):
    revisao = _enviar(cliente, p["proj"], obra, "004")
    assert cliente.post(f"/revisoes/{revisao['id']}/publicar", json={}, headers=p["coord"]).status_code == 200

    r = _reprovar(cliente, p["coord"], revisao)
    assert r.status_code == 409

    outra = _enviar(cliente, p["proj"], obra, "005")
    assert _reprovar(cliente, p["coord"], outra).status_code == 200
    assert _reprovar(cliente, p["coord"], outra).status_code == 409
    # Reprovada não se libera nem recebe arquivo.
    r = cliente.post(f"/revisoes/{outra['id']}/publicar", json={}, headers=p["coord"])
    assert r.status_code == 409
    r = enviar_arquivo(cliente, p["proj"], obra["id"], f"{OBRA}-ARQ-PE-005-R00.dwg", b"AC1032" + b"\x00" * 200)
    assert r.status_code == 409


def test_a_obra_nao_ve_a_reprovada(cliente, p, obra):
    r00 = _enviar(cliente, p["proj"], obra, "006")
    assert cliente.post(f"/revisoes/{r00['id']}/publicar", json={}, headers=p["coord"]).status_code == 200
    r01 = _enviar(cliente, p["proj"], obra, "006", "01", autorizar_com=p["coord"])
    assert _reprovar(cliente, p["coord"], r01).status_code == 200

    assert cliente.get(f"/revisoes/{r01['id']}", headers=p["campo"]).status_code == 404
    doc = cliente.get(f"/obras/{obra['id']}/documentos?busca={OBRA}-ARQ-PE-006", headers=p["campo"]).json()
    atual = doc["itens"][0]["revisao_atual"]
    assert (atual["numero"], atual["status"]) == ("00", "liberado_para_obra")

    # A equipe vê a reprovada no histórico, e a R00 segue valendo.
    equipe = cliente.get(f"/documentos/{doc['itens'][0]['id']}", headers=p["proj"]).json()
    status = {rv["numero"]: rv["status"] for rv in equipe["revisoes"]}
    assert status == {"01": "reprovado", "00": "liberado_para_obra"}


def test_baixar_a_reprovada_avisa(cliente, p, obra):
    revisao = _enviar(cliente, p["proj"], obra, "007")
    assert _reprovar(cliente, p["coord"], revisao).status_code == 200
    arquivo = cliente.get(f"/revisoes/{revisao['id']}", headers=p["proj"]).json()["arquivos"][0]

    r = cliente.get(f"/arquivos/{arquivo['id']}/download", headers=p["proj"])

    assert r.status_code == 200, r.text
    assert "REPROVADA" in r.json()["aviso"]


# ------------------------------------------------------------ correção


def test_correcao_vem_numa_revisao_nova_sem_outra_autorizacao(cliente, p, obra):
    r00 = _enviar(cliente, p["proj"], obra, "008")
    assert _reprovar(cliente, p["coord"], r00).status_code == 200

    r01 = _enviar(cliente, p["proj"], obra, "008", "01")
    assert r01["numero"] == "01"
    assert r01["status"] == "em_revisao"


def test_reprovada_depois_de_liberada_tambem_dispensa_autorizacao(cliente, p, obra):
    r00 = _enviar(cliente, p["proj"], obra, "009")
    assert cliente.post(f"/revisoes/{r00['id']}/publicar", json={}, headers=p["coord"]).status_code == 200
    r01 = _enviar(cliente, p["proj"], obra, "009", "01", autorizar_com=p["coord"])
    assert _reprovar(cliente, p["coord"], r01).status_code == 200

    r02 = _enviar(cliente, p["proj"], obra, "009", "02")
    assert r02["numero"] == "02"


# ------------------------------------------------------------ liberar


def test_liberar_com_observacao_opcional(cliente, p, obra):
    sem = _enviar(cliente, p["proj"], obra, "010")
    r = cliente.post(f"/revisoes/{sem['id']}/publicar", json={}, headers=p["coord"])
    assert r.status_code == 200, r.text
    assert r.json()["observacao"] is None

    com = _enviar(cliente, p["proj"], obra, "011")
    r = cliente.post(
        f"/revisoes/{com['id']}/publicar",
        json={"observacao": "  Liberado; conferir cota do reservatório na obra.  "},
        headers=p["coord"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["observacao"] == "Liberado; conferir cota do reservatório na obra."


# ------------------------------------------------------------ avisos


def test_reprovar_avisa_so_quem_enviou_com_a_observacao(cliente, admin, p, obra):
    revisao = _enviar(cliente, p["proj"], obra, "012")
    _limpar(cliente, admin, *p.values())

    assert _reprovar(cliente, p["coord"], revisao).status_code == 200

    avisos = _avisos(cliente, p["proj"])
    assert [a["tipo"] for a in avisos] == ["revisao_reprovada"]
    assert avisos[0]["titulo"] == f"R00 reprovada · {OBRA}-ARQ-PE-012"
    assert OBS in avisos[0]["texto"]
    assert "Coordanc Souza reprovou a R00" in avisos[0]["texto"]
    for quem in ("outro", "campo", "coord"):
        assert _avisos(cliente, p[quem]) == [], quem


class _SmtpFalso:
    enviados: list = []

    def __init__(self, host, porta, timeout=None):
        pass

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


def test_reprovar_manda_email_com_a_observacao(cliente, p, obra, monkeypatch):
    import app.services.email as modulo

    monkeypatch.setattr(settings, "email_smtp_host", "smtp.exemplo.com")
    monkeypatch.setattr(settings, "email_smtp_usuario", "usuario")
    monkeypatch.setattr(settings, "email_smtp_senha", "senha")
    monkeypatch.setattr(settings, "email_remetente", "Treèle Projetos <projetos@treele.com.br>")
    monkeypatch.setattr(modulo.smtplib, "SMTP", _SmtpFalso)
    _SmtpFalso.enviados = []
    revisao = _enviar(cliente, p["proj"], obra, "013")
    _SmtpFalso.enviados = []

    assert _reprovar(cliente, p["coord"], revisao).status_code == 200

    assert [m["To"] for m in _SmtpFalso.enviados] == ["projanc@anc.teste.com.br"]
    msg = _SmtpFalso.enviados[0]
    assert msg["Subject"] == f"[{OBRA}] R00 reprovada · {OBRA}-ARQ-PE-013"
    assert OBS in msg.get_body(preferencelist=("plain",)).get_content()
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "Revisão reprovada" in html
