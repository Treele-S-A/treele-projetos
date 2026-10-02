"""Solicitação de revisão: a obra pede, o projeto atende.

Regras da TREELE (02/10/2026):

- Quem pede é o coordenador ou a obra, sempre dizendo o que deve mudar.
- Fotos e PDFs marcados podem ir junto; prazo e urgência, não.
- O pedido é sobre o projeto LIBERADO para obra — é o que está sendo
  executado. Vários pedidos podem estar abertos ao mesmo tempo.
- Fecha sozinho quando a revisão nova é liberada para obra: o status do
  documento continua "liberado" até lá, com a marca de "revisão solicitada"
  ao lado (decisão de 18/09/2026).
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..enums import StatusArquivo, StatusSolicitacao
from ..models import Revisao, SolicitacaoRevisao
from ..schemas import AnexoOut, SolicitacaoOut, UsuarioOut

DESCRICAO_MIN = 10
DESCRICAO_MAX = 4000

ANEXO_MAX_MB = 25
ANEXO_MAX_POR_SOLICITACAO = 10

# Extensão → tipo. Só o que o navegador mostra sozinho: foto e PDF.
TIPOS_ANEXO = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def problema_no_pedido(descricao: str | None) -> str | None:
    if not descricao:
        return "Descreva o que deve mudar no projeto."
    if len(descricao) < DESCRICAO_MIN:
        return f"A descrição precisa ter ao menos {DESCRICAO_MIN} caracteres."
    if len(descricao) > DESCRICAO_MAX:
        return f"A descrição pode ter no máximo {DESCRICAO_MAX} caracteres."
    return None


def tipo_do_anexo(nome: str) -> str | None:
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    return TIPOS_ANEXO.get(extensao)


def saida(solicitacao: SolicitacaoRevisao) -> SolicitacaoOut:
    return SolicitacaoOut(
        id=solicitacao.id,
        descricao=solicitacao.descricao,
        status=solicitacao.status,
        criada_em=solicitacao.criada_em,
        criada_por=(
            UsuarioOut.model_validate(solicitacao.criada_por) if solicitacao.criada_por else None
        ),
        revisao_numero=solicitacao.revisao.numero if solicitacao.revisao else None,
        atendida_em=solicitacao.atendida_em,
        atendida_por_numero=(
            solicitacao.atendida_por_revisao.numero if solicitacao.atendida_por_revisao else None
        ),
        anexos=[
            AnexoOut.model_validate(a)
            for a in solicitacao.anexos
            if a.status == StatusArquivo.disponivel
        ],
    )


def abertas_por_documento(db: Session, documento_ids: list[int]) -> dict[int, int]:
    if not documento_ids:
        return {}
    return dict(
        db.execute(
            select(SolicitacaoRevisao.documento_id, func.count(SolicitacaoRevisao.id))
            .where(
                SolicitacaoRevisao.documento_id.in_(documento_ids),
                SolicitacaoRevisao.status == StatusSolicitacao.aberta,
            )
            .group_by(SolicitacaoRevisao.documento_id)
        ).all()
    )


def atender_ao_liberar(db: Session, revisao: Revisao) -> list[SolicitacaoRevisao]:
    """Fecha os pedidos abertos do documento: a revisão nova saiu. Não faz commit."""
    abertas = list(
        db.scalars(
            select(SolicitacaoRevisao).where(
                SolicitacaoRevisao.documento_id == revisao.documento_id,
                SolicitacaoRevisao.status == StatusSolicitacao.aberta,
            )
        )
    )
    agora = datetime.now(timezone.utc)
    for s in abertas:
        s.status = StatusSolicitacao.atendida
        s.atendida_em = agora
        s.atendida_por_revisao_id = revisao.id
    return abertas
