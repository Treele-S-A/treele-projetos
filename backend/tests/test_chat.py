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

    def fazer(usuario_id, leitor=None):
        db = SessionLocal()
        sessoes.append(db)
        return Ferramentas(db, db.get(Usuario, usuario_id), leitor=leitor)

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


# ------------------------------------------------------------ leitura do PDF


class _Leitor:
    """Leitor de mentira: guarda o que recebeu e devolve um texto fixo."""

    def __init__(self):
        self.chamadas = []

    def __call__(self, dados, pergunta, codigo):
        self.chamadas.append((dados, pergunta, codigo))
        return "Carimbo: escala 1:50. Nota 3: impermeabilizar o box."


def test_le_o_pdf_da_revisao_vigente_e_registra(cenario, ferramentas_de):
    from app.models import Evento
    from sqlalchemy import select

    leitor = _Leitor()
    f = ferramentas_de(cenario["ids"]["campo"], leitor)
    r = f.executar("ler_projeto", {"codigo": "CHA-ARQ-PE-001", "pergunta": "Qual a escala?"})
    assert r["leitura"].startswith("Carimbo: escala 1:50")
    assert r["revisao_lida"] == "R00"
    assert r["arquivo"] == "CHA-ARQ-PE-001-R00.pdf"
    assert "conferidas no PDF" in r["lembrete"]
    dados, pergunta, codigo = leitor.chamadas[0]
    assert dados == PDF and pergunta == "Qual a escala?" and codigo == "CHA-ARQ-PE-001"

    f.db.commit()
    evento = f.db.scalars(
        select(Evento).where(Evento.acao == "lido_pelo_assistente").order_by(Evento.id.desc())
    ).first()
    assert evento.detalhes["arquivo"] == "CHA-ARQ-PE-001-R00.pdf"
    assert evento.usuario_id == cenario["ids"]["campo"]


def test_leitura_segue_a_regra_do_download(cenario, ferramentas_de):
    leitor = _Leitor()
    campo = ferramentas_de(cenario["ids"]["campo"], leitor)
    # A obra não lê o que ainda está em revisão; o comercial só lê COM.
    assert "erro" in campo.ler_projeto(codigo="CHA-EST-PE-001", pergunta="x")
    comercial = ferramentas_de(cenario["ids"]["comercial"], leitor)
    assert "erro" in comercial.ler_projeto(codigo="CHA-ARQ-PE-001", pergunta="x")
    assert "leitura" in comercial.ler_projeto(codigo="CHA-COM-PE-001", pergunta="x")
    # O projetista lê a em revisão, com o aviso.
    proj = ferramentas_de(cenario["ids"]["proj"], leitor)
    r = proj.ler_projeto(codigo="CHA-EST-PE-001", pergunta="x")
    assert "EM REVISÃO" in r["aviso"]
    # Ninguém lê obra de que não participa.
    assert "erro" in campo.ler_projeto(codigo="CHB-ARQ-PE-001", pergunta="x")
    assert len(leitor.chamadas) == 2


def test_pdf_grande_demais_nao_vai_ao_modelo(cenario, ferramentas_de, monkeypatch):
    monkeypatch.setattr(settings, "chat_pdf_max_mb", 0)
    leitor = _Leitor()
    r = ferramentas_de(cenario["ids"]["proj"], leitor).ler_projeto(
        codigo="CHA-ARQ-PE-001", pergunta="x"
    )
    assert "assistente lê até 0 MB" in r["erro"]
    assert leitor.chamadas == []


def test_revisao_pedida_que_nao_existe(cenario, ferramentas_de):
    r = ferramentas_de(cenario["ids"]["proj"], _Leitor()).ler_projeto(
        codigo="CHA-ARQ-PE-001", pergunta="x", revisao="R07"
    )
    assert "R07" in r["erro"]


def test_leitura_vai_ao_modelo_como_pdf(monkeypatch):
    corpos = []

    def falso(corpo, tempo=None):
        corpos.append((corpo, tempo))
        return {"candidates": [{"content": {"parts": [{"text": "Nota 1: concreto C30."}]}}]}

    monkeypatch.setattr(chat_modelo, "_chamar", falso)
    texto = chat_modelo.ler_pdf(PDF, "Quais as notas?", "CHA-ARQ-PE-001")
    assert texto == "Nota 1: concreto C30."
    corpo, tempo = corpos[0]
    partes = corpo["contents"][0]["parts"]
    assert partes[0]["inlineData"]["mimeType"] == "application/pdf"
    assert "Quais as notas?" in partes[1]["text"]
    assert tempo == chat_modelo.TEMPO_LEITURA_PDF


def test_consulta_sem_parametro_nao_declara_objeto_vazio():
    """O Gemini recusa "parameters" com "properties" vazio — e a recusa derruba
    todas as perguntas (caso real, 07/10/2026)."""
    from app.services.chat_ferramentas import DECLARACOES

    for d in DECLARACOES:
        if "parameters" in d:
            assert d["parameters"]["properties"], d["name"]
            for campo in d["parameters"]["properties"].values():
                if "enum" in campo:
                    assert campo.get("format") == "enum", d["name"]


def test_administrador_ve_o_motivo_tecnico_e_os_outros_nao(cliente, admin, cenario, monkeypatch):
    class Resposta:
        status_code = 400
        text = ""

        def json(self):
            return {"error": {"message": "Invalid JSON payload received."}}

    monkeypatch.setattr(settings, "gemini_api_key", "chave-de-teste")
    monkeypatch.setattr(chat_modelo.httpx, "post", lambda *a, **k: Resposta())
    corpo = {"mensagens": [{"papel": "usuario", "texto": "Oi"}]}

    r = cliente.post("/chat", json=corpo, headers=admin)
    assert r.status_code == 503
    assert "Detalhe técnico: 400 Invalid JSON payload received." in r.json()["detail"]

    campo = autenticar(cliente, "campo@cht.teste.com.br", SENHA)
    r = cliente.post("/chat", json=corpo, headers=campo)
    assert "Detalhe técnico" not in r.json()["detail"]
