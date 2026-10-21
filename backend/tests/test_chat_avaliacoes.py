"""👍/👎 nas respostas do chat (TREELE, 21/10/2026): a resposta avaliada fica
guardada com a conversa e as etapas, para saber onde o assistente erra."""

import pytest

from app.config import settings

from .conftest import autenticar

SENHA = "senha-aval-12345"
CONVERSA = [
    {"papel": "usuario", "texto": "Qual o volume da caixa d'água da Milos?"},
    {"papel": "assistente", "texto": "Não encontrei o volume."},
]


@pytest.fixture(scope="module")
def pessoas(cliente, admin):
    obra = cliente.post("/obras", json={"codigo": "AVL", "nome": "Obra avaliação"}, headers=admin).json()
    outra = cliente.post("/obras", json={"codigo": "AVX", "nome": "Outra"}, headers=admin).json()
    cabs = {}
    for apelido in ("ana", "bia"):
        email = f"{apelido}@aval.teste.com.br"
        u = cliente.post("/usuarios", json={"nome": apelido.title(), "email": email, "senha": SENHA},
                         headers=admin).json()
        cliente.post(f"/obras/{obra['id']}/membros", json={"usuario_id": u["id"], "papel": "obra"},
                     headers=admin)
        cabs[apelido] = autenticar(cliente, email, SENHA)
    return {"obra": obra, "outra": outra, **cabs}


@pytest.fixture(autouse=True)
def _claude(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "chave-de-teste")
    monkeypatch.setattr(settings, "chat_fornecedor", "")


def _avaliar(cliente, cab, **extra):
    corpo = {"conversa": CONVERSA, "etapas": ["Lendo o PDF de MIL-HID-PE-AF"], "nota": -1, **extra}
    return cliente.post("/chat/avaliacoes", json=corpo, headers=cab)


def test_avaliacao_guarda_conversa_etapas_e_quem_respondeu(cliente, admin, pessoas):
    r = _avaliar(cliente, pessoas["ana"], obra_id=pessoas["obra"]["id"],
                 comentario="  Está na prancha: 1000 litros.  ")
    assert r.status_code == 201, r.text
    lista = cliente.get("/chat/avaliacoes", headers=admin).json()
    a = next(x for x in lista if x["id"] == r.json()["id"])
    assert a["nota"] == -1 and a["comentario"] == "Está na prancha: 1000 litros."
    assert a["conversa"] == CONVERSA and a["etapas"] == ["Lendo o PDF de MIL-HID-PE-AF"]
    assert (a["fornecedor"], a["modelo"]) == ("claude", settings.chat_modelo_claude)
    assert (a["usuario"], a["obra"]) == ("Ana", "AVL")


def test_obra_que_a_pessoa_nao_ve_nao_fica_registrada(cliente, admin, pessoas):
    r = _avaliar(cliente, pessoas["ana"], obra_id=pessoas["outra"]["id"])
    a = next(x for x in cliente.get("/chat/avaliacoes", headers=admin).json() if x["id"] == r.json()["id"])
    assert a["obra"] is None


def test_trocar_voto_e_comentar_so_na_propria(cliente, admin, pessoas):
    aid = _avaliar(cliente, pessoas["ana"]).json()["id"]
    assert cliente.patch(f"/chat/avaliacoes/{aid}", json={"nota": 1}, headers=pessoas["ana"]).status_code == 204
    assert cliente.patch(f"/chat/avaliacoes/{aid}", json={"comentario": "Errou a revisão."},
                         headers=pessoas["ana"]).status_code == 204
    # A outra pessoa não mexe na avaliação de ninguém.
    assert cliente.patch(f"/chat/avaliacoes/{aid}", json={"nota": -1}, headers=pessoas["bia"]).status_code == 404
    a = next(x for x in cliente.get("/chat/avaliacoes", headers=admin).json() if x["id"] == aid)
    assert (a["nota"], a["comentario"]) == (1, "Errou a revisão.")
    assert a["atualizada_em"]
    positivas = cliente.get("/chat/avaliacoes?nota=1", headers=admin).json()
    assert aid in {x["id"] for x in positivas} and all(x["nota"] == 1 for x in positivas)


def test_lista_so_para_administrador(cliente, pessoas):
    assert cliente.get("/chat/avaliacoes", headers=pessoas["ana"]).status_code == 403


def test_pedido_mal_formado(cliente, pessoas):
    so_pergunta = [CONVERSA[0], {"papel": "usuario", "texto": "E agora?"}]
    assert cliente.post("/chat/avaliacoes", json={"conversa": so_pergunta, "nota": 1},
                        headers=pessoas["ana"]).status_code == 422
    assert _avaliar(cliente, pessoas["ana"], nota=0).status_code == 422
    assert cliente.post("/chat/avaliacoes", json={"conversa": CONVERSA, "nota": 1}).status_code == 401


# ------------------------------------------------- e-mail a cada 👎 (21/10/2026)


@pytest.fixture
def emails(monkeypatch):
    import app.services.email as modulo

    enviados = []
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.exemplo.com")
    monkeypatch.setattr(settings, "chat_avisar_avaliacoes", "estagio.projetos@treele.com.br")
    monkeypatch.setattr(modulo, "enviar", lambda ms: enviados.extend(ms) or [True] * len(ms))
    return enviados


def test_negativo_avisa_so_o_endereco_configurado(cliente, pessoas, emails):
    r = _avaliar(cliente, pessoas["ana"], obra_id=pessoas["obra"]["id"])
    assert r.status_code == 201, r.text
    assert [m.para for m in emails] == ["estagio.projetos@treele.com.br"]
    m = emails[0]
    assert m.assunto.startswith(f"[Chat] 👎 nº {r.json()['id']} · Qual o volume")
    assert "Ana marcou 👎" in m.texto and "Não encontrei o volume." in m.texto
    assert "Lendo o PDF de MIL-HID-PE-AF" in m.texto
    assert "Chat · 👎" in m.html and "AVL · Obra avaliação" in m.html

    # O comentário chega depois, num segundo e-mail com o mesmo assunto.
    cliente.patch(f"/chat/avaliacoes/{r.json()['id']}", json={"comentario": "A prancha diz 1000 L."},
                  headers=pessoas["ana"])
    assert len(emails) == 2 and emails[1].assunto == m.assunto
    assert "A prancha diz 1000 L." in emails[1].texto and "Ana explicou" in emails[1].texto


def test_positivo_nao_avisa_e_virar_negativo_avisa(cliente, pessoas, emails):
    r = _avaliar(cliente, pessoas["bia"], nota=1)
    assert emails == []
    cliente.patch(f"/chat/avaliacoes/{r.json()['id']}", json={"nota": -1}, headers=pessoas["bia"])
    assert len(emails) == 1 and "Bia marcou 👎" in emails[0].texto


def test_sem_destinatario_nao_avisa(cliente, pessoas, emails, monkeypatch):
    monkeypatch.setattr(settings, "chat_avisar_avaliacoes", "")
    _avaliar(cliente, pessoas["ana"])
    assert emails == []
