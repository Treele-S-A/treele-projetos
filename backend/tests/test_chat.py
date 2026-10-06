"""Chat do acervo (Fase 2): as consultas obedecem às regras da tela, e o ciclo
com o modelo funciona — testado com um modelo de mentira, sem rede."""

import pytest

from app.config import settings
from app.db import SessionLocal
from app.models import Usuario
from app.services import chat_modelo
from app.services.chat_ferramentas import Ferramentas

from .conftest import autenticar, enviar_arquivo

PDF = b"%PDF-1.7\n" + b"0" * 200
SENHA = "senha-cht-12345"


def _usuario(cliente, admin, email, nome, obra=None, papel=None, comercial=False):
    corpo = {"nome": nome, "email": email, "senha": SENHA, "comercial": comercial}
    r = cliente.post("/usuarios", json=corpo, headers=admin)
    assert r.status_code == 201, r.text
    if obra:
        cliente.post(
            f"/obras/{obra['id']}/membros",
            json={"usuario_id": r.json()["id"], "papel": papel}, headers=admin,
        )
    return r.json()["id"]


def _enviar(cliente, admin, obra, nome, liberar, titulo):
    r = enviar_arquivo(cliente, admin, obra["id"], nome, PDF, titulo=titulo,
                       descricao="Primeira emissão.")
    assert r.status_code == 200, r.text
    if liberar:
        cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={}, headers=admin)


@pytest.fixture(scope="module")
def cenario(cliente, admin):
    a = cliente.post("/obras", json={"codigo": "CHA", "nome": "Obra chat A"}, headers=admin).json()
    b = cliente.post("/obras", json={"codigo": "CHB", "nome": "Obra chat B"}, headers=admin).json()
    _enviar(cliente, admin, a, "CHA-ARQ-PE-001-R00.pdf", True, "Planta baixa do térreo")
    _enviar(cliente, admin, a, "CHA-EST-PE-001-R00.pdf", False, "Forma do térreo")
    _enviar(cliente, admin, a, "CHA-COM-PE-001-R00.pdf", True, "Folder de vendas")
    _enviar(cliente, admin, b, "CHB-ARQ-PE-001-R00.pdf", True, "Fachada")
    ids = {
        "campo": _usuario(cliente, admin, "campo@cht.teste.com.br", "Campo", a, "obra"),
        "proj": _usuario(cliente, admin, "proj@cht.teste.com.br", "Proj", a, "projetista"),
        "comercial": _usuario(cliente, admin, "com@cht.teste.com.br", "Comercial", comercial=True),
    }
    return {"a": a, "b": b, "ids": ids}


@pytest.fixture
def ferramentas_de():
    sessoes = []

    def fazer(usuario_id):
        db = SessionLocal()
        sessoes.append(db)
        return Ferramentas(db, db.get(Usuario, usuario_id))

    yield fazer
    for db in sessoes:
        db.close()


def _codigos(resultado):
    return {d["codigo"] for d in resultado["documentos"]}


# ------------------------------------------------------------ permissões


def test_obra_nao_ve_revisao_em_andamento(cenario, ferramentas_de):
    f = ferramentas_de(cenario["ids"]["campo"])
    assert _codigos(f.buscar_documentos(obra="CHA")) == {"CHA-ARQ-PE-001", "CHA-COM-PE-001"}
    assert "erro" in f.detalhar_documento("CHA-EST-PE-001")


def test_projetista_ve_tudo_da_obra(cenario, ferramentas_de):
    f = ferramentas_de(cenario["ids"]["proj"])
    assert "CHA-EST-PE-001" in _codigos(f.buscar_documentos(obra="CHA"))
    detalhe = f.detalhar_documento("CHA-EST-PE-001")
    assert detalhe["revisoes"][0]["status"] == "Em revisão"
    assert detalhe["link"].startswith("/documentos/")


def test_ninguem_ve_obra_de_que_nao_participa(cenario, ferramentas_de):
    f = ferramentas_de(cenario["ids"]["campo"])
    assert {o["codigo"] for o in f.listar_obras()["obras"]} == {"CHA"}
    assert "erro" in f.executar("buscar_documentos", {"obra": "CHB"})
    assert "erro" in f.detalhar_documento("CHB-ARQ-PE-001")
    # Sem obra, busca só nas que vê.
    assert not any(c.startswith("CHB") for c in _codigos(f.buscar_documentos()))


def test_comercial_so_ve_com_liberado(cenario, ferramentas_de):
    f = ferramentas_de(cenario["ids"]["comercial"])
    codigos = _codigos(f.buscar_documentos())
    assert codigos and all("-COM-" in c for c in codigos)
    assert "erro" in f.detalhar_documento("CHA-ARQ-PE-001")
    assert "erro" in f.listar_solicitacoes()
    assert "solicitacoes" not in f.detalhar_documento("CHA-COM-PE-001")


def test_filtros_e_resumos(cenario, ferramentas_de):
    f = ferramentas_de(cenario["ids"]["proj"])
    assert _codigos(f.buscar_documentos(obra="CHA", disciplina="est")) == {"CHA-EST-PE-001"}
    assert _codigos(f.buscar_documentos(obra="CHA", texto="térreo")) == {
        "CHA-ARQ-PE-001", "CHA-EST-PE-001",
    }
    assert "erro" in f.buscar_documentos(disciplina="XYZ")
    resumo = f.resumo_da_obra(obra="CHA")
    assert resumo["documentos_por_disciplina_e_status"]["EST · Estrutura"] == {"Em revisão": 1}
    recentes = f.liberacoes_recentes(dias=3, obra="CHA")
    assert {i["codigo"] for i in recentes["liberacoes"]} == {"CHA-ARQ-PE-001", "CHA-COM-PE-001"}


def test_consulta_desconhecida_ou_mal_feita_vira_erro(cenario, ferramentas_de):
    f = ferramentas_de(cenario["ids"]["proj"])
    assert "erro" in f.executar("apagar_tudo", {})
    assert "erro" in f.executar("detalhar_documento", {"nao_existe": 1})


# ------------------------------------------------------------ ciclo com o modelo


@pytest.fixture
def modelo_falso(monkeypatch):
    """Primeiro pede uma consulta (com assinatura de pensamento), depois responde."""
    chamadas = []
    roteiro = [
        {"candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"name": "buscar_documentos", "args": {"obra": "CHA"}, "id": "c1"},
             "thoughtSignature": "assinatura-xyz"},
        ]}}]},
        {"candidates": [{"content": {"role": "model", "parts": [
            {"text": "pensando…", "thought": True},
            {"text": "Achei 2 documentos liberados."},
        ]}}]},
    ]

    def falso(corpo):
        chamadas.append(corpo)
        return roteiro[len(chamadas) - 1]

    monkeypatch.setattr(settings, "gemini_api_key", "chave-de-teste")
    monkeypatch.setattr(chat_modelo, "_chamar", falso)
    return chamadas


def test_pergunta_consulta_e_responde(cliente, cenario, modelo_falso):
    campo = autenticar(cliente, "campo@cht.teste.com.br", SENHA)
    r = cliente.post(
        "/chat",
        json={"mensagens": [{"papel": "usuario", "texto": "O que está liberado?"}],
              "obra_id": cenario["a"]["id"]},
        headers=campo,
    )
    assert r.status_code == 200, r.text
    # O pensamento do modelo não aparece para a pessoa.
    assert r.json()["resposta"] == "Achei 2 documentos liberados."

    primeira, segunda = modelo_falso
    assert "CHA · Obra chat A" in primeira["systemInstruction"]["parts"][0]["text"]
    assert "Campo" in primeira["systemInstruction"]["parts"][0]["text"]
    # A parte do modelo volta intacta, com a assinatura de pensamento.
    assert segunda["contents"][1]["parts"][0]["thoughtSignature"] == "assinatura-xyz"
    resposta = segunda["contents"][2]["parts"][0]["functionResponse"]
    assert resposta["id"] == "c1"
    # A consulta rodou com as permissões da obra: sem o que está em revisão.
    codigos = {d["codigo"] for d in resposta["response"]["documentos"]}
    assert codigos == {"CHA-ARQ-PE-001", "CHA-COM-PE-001"}


def test_obra_da_tela_que_a_pessoa_nao_ve_nao_entra_no_contexto(cliente, cenario, modelo_falso):
    campo = autenticar(cliente, "campo@cht.teste.com.br", SENHA)
    cliente.post(
        "/chat",
        json={"mensagens": [{"papel": "usuario", "texto": "Oi"}], "obra_id": cenario["b"]["id"]},
        headers=campo,
    )
    assert "Obra chat B" not in modelo_falso[0]["systemInstruction"]["parts"][0]["text"]


def test_desligado_sem_chave(cliente, admin, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert cliente.get("/chat/estado", headers=admin).json() == {"ligado": False}
    r = cliente.post("/chat", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]}, headers=admin)
    assert r.status_code == 503


def test_limite_do_plano_gratuito_vira_mensagem_clara(cliente, admin, monkeypatch):
    class Resposta:
        status_code = 429
        text = "quota"

    monkeypatch.setattr(settings, "gemini_api_key", "chave-de-teste")
    monkeypatch.setattr(chat_modelo.httpx, "post", lambda *a, **k: Resposta())
    r = cliente.post("/chat", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]}, headers=admin)
    assert r.status_code == 503
    assert "limite gratuito" in r.json()["detail"]


def test_exige_login(cliente):
    assert cliente.post("/chat", json={"mensagens": [{"papel": "usuario", "texto": "Oi"}]}).status_code == 401
