"""Chat do acervo com o Claude (16/10/2026): a escolha do fornecedor, o ciclo
de consultas no formato da Anthropic e as mensagens de erro — sem rede."""

import json

import pytest

from app.config import settings
from app.services import chat_claude, chat_modelo
from app.services.chat_ferramentas import DECLARACOES

from .test_chat import PDF, SENHA, _enviar, _usuario


@pytest.fixture(scope="module")
def cenario(cliente, admin):
    a = cliente.post("/obras", json={"codigo": "CLA", "nome": "Obra Claude", "endereco": "Rua de Teste, 100 – Centro – Curitiba – PR"}, headers=admin).json()
    _enviar(cliente, admin, a, "CLA-ARQ-PE-001-R00.pdf", True, "Planta baixa do térreo")
    _enviar(cliente, admin, a, "CLA-EST-PE-001-R00.pdf", False, "Forma do térreo")
    _enviar(cliente, admin, a, "CLA-COM-PE-001-R00.pdf", True, "Folder de vendas")
    _usuario(cliente, admin, "campo@cla.teste.com.br", "Campo", a, "obra")
    return {"a": a}


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "chave-de-teste")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "chat_fornecedor", "")
    monkeypatch.setattr(chat_claude, "PAUSA_ANTES_DE_REPETIR", 0)


class Resposta:
    def __init__(self, status, corpo, cabecalhos=None):
        self.status_code = status
        self._corpo = corpo
        self.headers = cabecalhos or {}
        self.text = json.dumps(corpo)

    def json(self):
        return self._corpo


# ------------------------------------------------------------ escolha


@pytest.mark.parametrize(
    "anthropic, gemini, forcado, esperado",
    [
        ("a", "", "", "claude"),
        ("", "g", "", "gemini"),
        ("a", "g", "", "claude"),
        ("a", "g", "gemini", "gemini"),
        ("", "g", "claude", None),  # forçou o Claude sem a chave dele: desligado
        ("", "", "", None),
    ],
)
def test_escolha_do_fornecedor(monkeypatch, anthropic, gemini, forcado, esperado):
    monkeypatch.setattr(settings, "anthropic_api_key", anthropic)
    monkeypatch.setattr(settings, "gemini_api_key", gemini)
    monkeypatch.setattr(settings, "chat_fornecedor", forcado)
    assert settings.chat_fornecedor_ativo == esperado
    assert settings.chat_ligado is (esperado is not None)


def test_estado_diz_quem_responde(cliente, admin, claude):
    r = cliente.get("/chat/estado", headers=admin)
    assert r.json() == {"ligado": True, "fornecedor": "Claude, da Anthropic"}


# ------------------------------------------------------------ formato


def test_ferramentas_no_formato_da_anthropic():
    convertidas = {f["name"]: f for f in chat_claude.ferramentas_claude()}
    assert set(convertidas) == {d["name"] for d in DECLARACOES}
    # Sem parâmetro: objeto vazio (a Anthropic exige input_schema).
    assert convertidas["listar_obras"]["input_schema"] == {"type": "object", "properties": {}}
    status = convertidas["buscar_documentos"]["input_schema"]["properties"]["status"]
    assert status["type"] == "string" and "format" not in status and status["enum"]
    assert convertidas["ler_projeto"]["input_schema"]["required"] == ["codigo", "pergunta"]


def test_pergunta_consulta_e_responde(cliente, cenario, claude, monkeypatch):
    corpos = []
    roteiro = [
        {"stop_reason": "tool_use", "content": [
            {"type": "text", "text": "Vou buscar."},
            {"type": "tool_use", "id": "t1", "name": "buscar_documentos", "input": {"obra": "CLA"}},
            {"type": "tool_use", "id": "t2", "name": "nao_existe", "input": {}},
        ]},
        {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Achei 2 liberados."}]},
    ]

    def falso(corpo, tempo=None):
        corpos.append(json.loads(json.dumps(corpo)))
        return roteiro[len(corpos) - 1]

    monkeypatch.setattr(chat_claude, "_chamar", falso)
    campo = cliente.post("/auth/login", json={"email": "campo@cla.teste.com.br",
                                              "senha": SENHA}).json()["token"]
    r = cliente.post("/chat", json={"mensagens": [{"papel": "usuario", "texto": "O que tem?"}],
                                    "obra_id": cenario["a"]["id"]},
                     headers={"Authorization": f"Bearer {campo}"})
    assert r.status_code == 200, r.text
    assert r.json()["resposta"] == "Achei 2 liberados."

    primeiro, segundo = corpos
    assert primeiro["model"] == settings.chat_modelo_claude
    assert primeiro["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "CLA · Obra Claude" in primeiro["system"][0]["text"]
    # A resposta do modelo volta intacta, e os resultados na ordem dos pedidos.
    assert segundo["messages"][1] == {"role": "assistant", "content": roteiro[0]["content"]}
    r1, r2 = segundo["messages"][2]["content"]
    assert (r1["tool_use_id"], r2["tool_use_id"]) == ("t1", "t2")
    # Quem é da obra não vê o EST em revisão — a regra da tela vale aqui também.
    codigos = {d["codigo"] for d in json.loads(r1["content"])["documentos"]}
    assert codigos == {"CLA-ARQ-PE-001", "CLA-COM-PE-001"}
    assert r2["is_error"] is True and "is_error" not in r1


def test_leitura_vai_como_documento_pdf(claude, monkeypatch):
    corpos = []

    def falso(corpo, tempo=None):
        corpos.append((corpo, tempo))
        return {"content": [{"type": "text", "text": "Nota 1: concreto C30."}]}

    monkeypatch.setattr(chat_claude, "_chamar", falso)
    assert chat_modelo.ler_pdf(PDF, "Quais as notas?", "CHA-ARQ-PE-001") == "Nota 1: concreto C30."
    corpo, tempo = corpos[0]
    documento, pergunta = corpo["messages"][0]["content"]
    assert documento["type"] == "document"
    assert documento["source"]["media_type"] == "application/pdf"
    assert "Quais as notas?" in pergunta["text"]
    assert tempo == chat_modelo.TEMPO_LEITURA_PDF


# ------------------------------------------------------------ erros


def test_sobrecarga_repete_uma_vez(cliente, admin, claude, monkeypatch):
    respostas = [
        Resposta(529, {"error": {"type": "overloaded_error", "message": "Overloaded"}}),
        Resposta(200, {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Oi."}]}),
    ]
    monkeypatch.setattr(chat_claude.httpx, "post", lambda *a, **k: respostas.pop(0))
    r = cliente.post("/chat", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]}, headers=admin)
    assert r.status_code == 200 and r.json()["resposta"] == "Oi."


def test_limite_por_minuto_com_espera_longa_nao_repete(cliente, admin, claude, monkeypatch):
    chamadas = []
    erro = Resposta(429, {"error": {"type": "rate_limit_error", "message": "slow down"}},
                    {"retry-after": "40"})
    monkeypatch.setattr(chat_claude.httpx, "post", lambda *a, **k: chamadas.append(1) or erro)
    r = cliente.post("/chat", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]}, headers=admin)
    assert r.status_code == 503
    assert "Espere um minuto" in r.json()["detail"]
    assert len(chamadas) == 1


def test_credito_esgotado_vira_mensagem_clara(cliente, admin, claude, monkeypatch):
    erro = Resposta(400, {"error": {"type": "invalid_request_error",
                                    "message": "Your credit balance is too low to access the API."}})
    monkeypatch.setattr(chat_claude.httpx, "post", lambda *a, **k: erro)
    r = cliente.post("/chat", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]}, headers=admin)
    assert r.status_code == 503
    assert "créditos do assistente acabaram" in r.json()["detail"]
    assert "credit balance" in r.json()["detail"]  # administrador vê o motivo técnico


def test_chave_recusada(cliente, admin, claude, monkeypatch):
    erro = Resposta(401, {"error": {"type": "authentication_error", "message": "invalid x-api-key"}})
    monkeypatch.setattr(chat_claude.httpx, "post", lambda *a, **k: erro)
    r = cliente.post("/chat", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]}, headers=admin)
    assert r.status_code == 503 and "chave recusada" in r.json()["detail"]


def test_chave_da_organizacao_manda_o_workspace(claude, monkeypatch):
    """Chave criada fora de um workspace: a Anthropic exige o ID dele."""
    cabecalhos = []
    ok = Resposta(200, {"content": [{"type": "text", "text": "ok"}]})
    monkeypatch.setattr(chat_claude.httpx, "post",
                        lambda *a, **k: cabecalhos.append(k["headers"]) or ok)
    chat_claude._chamar({"model": "m"})
    assert "anthropic-workspace-id" not in cabecalhos[0]
    monkeypatch.setattr(settings, "anthropic_workspace_id", " wrkspc_teste ")
    chat_claude._chamar({"model": "m"})
    assert cabecalhos[1]["anthropic-workspace-id"] == "wrkspc_teste"
