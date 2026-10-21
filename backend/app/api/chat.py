"""Chat do acervo (Fase 2, 06/10/2026).

Pergunta em português, resposta com base nas consultas ao catálogo — com as
permissões de quem pergunta. A conversa não fica guardada no servidor: a tela
manda o histórico a cada pergunta e esquece ao fechar.
"""

import json
import logging
import queue
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal, get_db
from ..deps import usuario_atual
from ..models import Obra, ObraMembro, Usuario
from ..services import chat_modelo
from ..services.chat_ferramentas import Ferramentas, catalogo

router = APIRouter(prefix="/chat", tags=["chat"])
log = logging.getLogger("treele.chat")

# Conversa longa custa mais (cota ou crédito) e confunde o modelo.
MAX_TURNOS = 12
MAX_CARACTERES = 2000


class TurnoEntrada(BaseModel):
    papel: str = Field(pattern="^(usuario|assistente)$")
    texto: str = Field(min_length=1, max_length=8000)


class PerguntaEntrada(BaseModel):
    mensagens: list[TurnoEntrada] = Field(min_length=1)
    # A obra aberta na tela, para "esta obra" fazer sentido.
    obra_id: int | None = None


class RespostaSaida(BaseModel):
    resposta: str


class EstadoSaida(BaseModel):
    ligado: bool
    # Nome para a nota da tela: quem gera as respostas.
    fornecedor: str | None = None


FORNECEDORES = {"claude": "Claude, da Anthropic", "gemini": "Google Gemini"}


@router.get("/estado", response_model=EstadoSaida)
def estado(usuario: Usuario = Depends(usuario_atual)):
    return EstadoSaida(
        ligado=settings.chat_ligado,
        fornecedor=FORNECEDORES.get(settings.chat_fornecedor_ativo or ""),
    )


def _papeis(db: Session, usuario: Usuario) -> str:
    if usuario.admin:
        return "administrador (vê tudo, em todas as obras)"
    if usuario.comercial:
        return "comercial (vê só a disciplina COM liberada para obra, em todas as obras)"
    papeis = [
        f"{m.obra.codigo}: {m.papel.value}"
        for m in db.query(ObraMembro).filter(ObraMembro.usuario_id == usuario.id)
    ]
    return "papéis por obra — " + (", ".join(papeis) or "nenhuma obra")


def _instrucoes(db: Session, usuario: Usuario, obra: Obra | None) -> str:
    hoje = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y")
    return f"""Você é o assistente do sistema de projetos da Treèle Construtora. Responde
dúvidas sobre o acervo de projetos: documentos (pranchas), revisões, status,
liberações e solicitações de revisão.

Regras:
- Responda em português do Brasil, curto e direto.
- Use SOMENTE o que as consultas devolverem. Nunca invente código, número de
  revisão, data, pessoa ou status. Se a consulta não trouxer, diga que não
  encontrou.
- Ao citar um documento, use link em markdown com o "link" da consulta, assim:
  [TRE-ARQ-PE-001 — Planta baixa](/documentos/12).
- Para perguntas sobre o conteúdo de uma prancha (carimbo, notas, legendas,
  ambientes, tabela de revisões), use ler_projeto. Ao responder com base nele,
  diga qual revisão foi lida e lembre que medidas e cotas devem ser
  conferidas no PDF.
- Você só consulta. Para alterar algo (enviar, liberar, autorizar), diga onde
  a pessoa faz isso na tela, conforme o guia abaixo.
- Se a pergunta for sobre outra coisa que não o acervo de projetos, diga com
  gentileza que só ajuda com o acervo.
- Listas longas: mostre os mais relevantes e diga quantos são no total.

Contexto:
- Hoje: {hoje}.
- Quem pergunta: {usuario.nome}, {_papeis(db, usuario)}.
- Obra aberta na tela: {f"{obra.codigo} · {obra.nome}" if obra else "nenhuma"}. Quando a
  pergunta não disser a obra, ou disser "esta obra", use essa.
- Status das revisões: Em revisão (em análise crítica do coordenador),
  Liberado para obra (vale para execução), Reprovada (reprovada na análise,
  com observação; a correção vem numa revisão nova), Obsoleto (substituído),
  Cancelado.
- {catalogo(db)}

Onde cada coisa fica na tela (cada pessoa só vê o que o papel dela permite):
- Menu da obra: Acervo (lista dos documentos, com filtros), Enviar arquivos,
  Configurações da obra e Registro de atividades (estes dois, coordenador).
- Enviar revisão nova: menu Enviar arquivos. O nome do arquivo segue o padrão
  de nomenclatura, e o sistema confere ao enviar.
- Liberar para obra ou reprovar uma revisão em análise: na página do
  documento, no quadro da revisão. Várias de uma vez: no Acervo, filtrar por
  status Em revisão, marcar as linhas e usar "Liberar para obra…".
- Solicitar revisão de um projeto liberado: na página do documento, botão
  "Solicitar revisão", descrevendo o que deve mudar (dá para anexar arquivos).
  O coordenador autoriza ou recusa ali mesmo.
- Cancelar uma revisão: na página do documento (coordenador, enquanto está em
  análise; administrador, a qualquer tempo). Nada é excluído do histórico."""


class Recusa(Exception):
    """Pedido que não chega ao modelo: chat desligado ou conversa mal formada."""

    def __init__(self, codigo: int, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo


def _conferir_pedido(dados: PerguntaEntrada) -> None:
    if not settings.chat_ligado:
        raise Recusa(status.HTTP_503_SERVICE_UNAVAILABLE, "O assistente está desligado.")
    if dados.mensagens[-1].papel != "usuario":
        raise Recusa(status.HTTP_422_UNPROCESSABLE_ENTITY, "A última mensagem é a pergunta.")


def _responder(db: Session, usuario: Usuario, dados: PerguntaEntrada, etapa=None) -> str:
    """A conversa inteira. Falha do modelo sai como ChatIndisponivel, com a
    mensagem para a pessoa (e o motivo técnico, se ela for administrador)."""
    ferramentas = Ferramentas(db, usuario, leitor=chat_modelo.ler_pdf, etapa=etapa)
    # Só entra no contexto a obra que a pessoa pode ver — o id vem da tela.
    obra = next((o for o in ferramentas._obras_visiveis() if o.id == dados.obra_id), None)
    historico = [
        chat_modelo.Turno(m.papel, m.texto[:MAX_CARACTERES])
        for m in dados.mensagens[-MAX_TURNOS:]
    ]
    try:
        resposta = chat_modelo.conversar(
            _instrucoes(db, usuario, obra), historico, ferramentas
        )
    except chat_modelo.ChatIndisponivel as erro:
        # PDF lido antes da falha também conta como leitura.
        db.commit()
        mensagem = str(erro)
        # O motivo técnico só para administrador: é quem configura o chat.
        if usuario.admin and erro.detalhe:
            mensagem += f" (Detalhe técnico: {erro.detalhe})"
        raise chat_modelo.ChatIndisponivel(mensagem) from erro
    db.commit()  # registro das leituras de PDF
    return resposta


@router.post("", response_model=RespostaSaida)
def perguntar(
    dados: PerguntaEntrada,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    try:
        _conferir_pedido(dados)
        return RespostaSaida(resposta=_responder(db, usuario, dados))
    except Recusa as erro:
        raise HTTPException(erro.codigo, str(erro)) from erro
    except chat_modelo.ChatIndisponivel as erro:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(erro)) from erro


@router.post("/fluxo")
def perguntar_com_etapas(dados: PerguntaEntrada, usuario: Usuario = Depends(usuario_atual)):
    """A mesma pergunta, com as etapas na tela enquanto o assistente trabalha
    (TREELE, 21/10/2026): cada consulta, o que ela trouxe e o que a IA diz
    entre uma e outra.

    Resposta em NDJSON, uma linha por evento:
    {"tipo": "etapa" | "resposta" | "erro", "texto": "..."}.
    A conversa roda numa thread com sessão de banco própria; a resposta vai
    saindo à medida que as etapas acontecem.
    """
    try:
        _conferir_pedido(dados)
    except Recusa as erro:
        raise HTTPException(erro.codigo, str(erro)) from erro

    fila: queue.Queue = queue.Queue()
    usuario_id = usuario.id

    def trabalhar() -> None:
        db = SessionLocal()
        try:
            pessoa = db.get(Usuario, usuario_id)
            resposta = _responder(db, pessoa, dados, etapa=lambda t: fila.put({"tipo": "etapa", "texto": t}))
            fila.put({"tipo": "resposta", "texto": resposta})
        except chat_modelo.ChatIndisponivel as erro:
            fila.put({"tipo": "erro", "texto": str(erro)})
        except Exception:  # noqa: BLE001 — a tela precisa de um fim, sempre
            log.exception("Chat: falha inesperada na conversa com etapas.")
            db.rollback()
            fila.put({"tipo": "erro", "texto": "O assistente não conseguiu responder agora. Tente de novo."})
        finally:
            db.close()
            fila.put(None)

    threading.Thread(target=trabalhar, daemon=True).start()

    def eventos():
        while (item := fila.get()) is not None:
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(
        eventos(),
        media_type="application/x-ndjson",
        # Sem isto, proxies seguram a resposta inteira e as etapas chegam
        # todas juntas no fim.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
