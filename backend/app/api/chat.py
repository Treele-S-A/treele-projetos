"""Chat do acervo (Fase 2, 06/10/2026).

Pergunta em português, resposta com base nas consultas ao catálogo — com as
permissões de quem pergunta. A conversa não fica guardada no servidor: a tela
manda o histórico a cada pergunta e esquece ao fechar.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import usuario_atual
from ..models import Obra, ObraMembro, Usuario
from ..services import chat_modelo
from ..services.chat_ferramentas import Ferramentas, catalogo

router = APIRouter(prefix="/chat", tags=["chat"])

# Conversa longa custa cota do plano gratuito e confunde o modelo.
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


@router.get("/estado", response_model=EstadoSaida)
def estado(usuario: Usuario = Depends(usuario_atual)):
    return EstadoSaida(ligado=settings.chat_ligado)


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
  a pessoa faz isso na tela.
- Se a pergunta for sobre outra coisa que não o acervo de projetos, diga com
  gentileza que só ajuda com o acervo.
- Listas longas: mostre os mais relevantes e diga quantos são no total.

Contexto:
- Hoje: {hoje}.
- Quem pergunta: {usuario.nome}, {_papeis(db, usuario)}.
- Obra aberta na tela: {f"{obra.codigo} · {obra.nome}" if obra else "nenhuma"}. Quando a
  pergunta não disser a obra, ou disser "esta obra", use essa.
- Status das revisões: Em revisão (ainda em elaboração), Liberado para obra
  (vale para execução), Obsoleto (substituído), Cancelado.
- {catalogo(db)}"""


@router.post("", response_model=RespostaSaida)
def perguntar(
    dados: PerguntaEntrada,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    if not settings.chat_ligado:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "O assistente está desligado.")
    if dados.mensagens[-1].papel != "usuario":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A última mensagem é a pergunta.")

    ferramentas = Ferramentas(db, usuario, leitor=chat_modelo.ler_pdf)
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
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, mensagem) from erro
    db.commit()  # registro das leituras de PDF
    return RespostaSaida(resposta=resposta)
