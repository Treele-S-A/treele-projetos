"""Chat com as etapas na tela (TREELE, 21/10/2026): a rota /chat/fluxo manda
cada consulta, o que ela trouxe e o que a IA diz entre uma e outra, e no fim
a resposta — uma linha JSON por evento."""

import json

import pytest

from app.config import settings
from app.services import chat_claude
from app.services.chat_ferramentas import descrever, resumir

from .test_chat import _enviar


@pytest.fixture(scope="module")
def obra(cliente, admin):
    o = cliente.post("/obras", json={"codigo": "ETP", "nome": "Obra etapas"}, headers=admin).json()
    _enviar(cliente, admin, o, "ETP-HID-PE-001-R00.pdf", True, "Água fria")
    _enviar(cliente, admin, o, "ETP-HID-PE-002-R00.pdf", True, "Esgoto")
    return o


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "chave-de-teste")
    monkeypatch.setattr(settings, "chat_fornecedor", "")


def _eventos(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(linha) for linha in r.text.splitlines() if linha.strip()]


def test_etapas_chegam_antes_da_resposta(cliente, admin, obra, claude, monkeypatch):
    roteiro = [
        {"stop_reason": "tool_use", "content": [
            {"type": "text", "text": "Vou buscar os projetos de hidráulica."},
            {"type": "tool_use", "id": "t1", "name": "buscar_documentos",
             "input": {"obra": "ETP", "disciplina": "HID"}},
        ]},
        {"stop_reason": "end_turn", "content": [{"type": "text", "text": "São 2 projetos."}]},
    ]
    monkeypatch.setattr(chat_claude, "_chamar", lambda corpo, tempo=None: roteiro.pop(0))
    r = cliente.post("/chat/fluxo", json={"mensagens": [{"papel": "usuario", "texto": "Hidráulica?"}]},
                     headers=admin)
    assert _eventos(r) == [
        {"tipo": "etapa", "texto": "Vou buscar os projetos de hidráulica."},
        {"tipo": "etapa", "texto": "Buscando documentos de HID na obra ETP"},
        {"tipo": "etapa", "texto": "2 documentos encontrados"},
        {"tipo": "resposta", "texto": "São 2 projetos."},
    ]


def test_falha_do_modelo_vira_evento_de_erro(cliente, admin, claude, monkeypatch):
    def falha(corpo, tempo=None):
        raise chat_claude.ChatIndisponivel("O assistente não respondeu a tempo.", "ReadTimeout")

    monkeypatch.setattr(chat_claude, "_chamar", falha)
    eventos = _eventos(cliente.post("/chat/fluxo", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]},
                                    headers=admin))
    assert eventos[-1]["tipo"] == "erro"
    assert "não respondeu a tempo" in eventos[-1]["texto"]
    assert "ReadTimeout" in eventos[-1]["texto"]  # administrador vê o motivo técnico


def test_erro_inesperado_tambem_termina_a_conversa(cliente, admin, claude, monkeypatch):
    def quebra(corpo, tempo=None):
        raise RuntimeError("bug")

    monkeypatch.setattr(chat_claude, "_chamar", quebra)
    eventos = _eventos(cliente.post("/chat/fluxo", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]},
                                    headers=admin))
    assert eventos == [{"tipo": "erro", "texto": "O assistente não conseguiu responder agora. Tente de novo."}]


def test_desligado_e_pedido_mal_formado_respondem_na_hora(cliente, admin, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    r = cliente.post("/chat/fluxo", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]}, headers=admin)
    assert r.status_code == 503
    monkeypatch.setattr(settings, "anthropic_api_key", "chave-de-teste")
    r = cliente.post("/chat/fluxo", json={"mensagens": [{"papel": "assistente", "texto": "Oi"}]}, headers=admin)
    assert r.status_code == 422
    assert cliente.post("/chat/fluxo", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]}).status_code == 401


def test_descricoes_das_consultas():
    assert descrever("ler_projeto", {"codigo": "MIL-HID-PE-AF", "revisao": "R02"}) == "Lendo o PDF de MIL-HID-PE-AF (R02)"
    assert descrever("buscar_documentos", {"status": "em_revisao", "texto": "térreo"}) == (
        "Buscando documentos com status Em revisão com “térreo”"
    )
    assert descrever("liberacoes_recentes", {}) == "Vendo as liberações dos últimos 7 dias"
    assert descrever("inventada", {}) == "Consultando o acervo"
    assert resumir({"total": 1, "documentos": [{}]}) == "1 documento encontrado"
    assert resumir({"erro": "Documento 'X' não encontrado."}) == "Não deu certo: Documento 'X' não encontrado."
    assert resumir({"link": "/documentos/1"}) is None
    # O histórico traz a lista de pedidos do documento: não é "0 solicitações".
    assert resumir({"codigo": "X", "revisoes": [{}, {}], "solicitacoes": []}) == "2 revisões no histórico"

