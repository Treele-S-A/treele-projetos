"""Solicitação de revisão: a obra pede, o coordenador autoriza, o projeto atende.

Regras da TREELE (02/10 e 05/10/2026):

- A obra pede, sempre dizendo o que deve mudar. Fotos e PDFs marcados podem
  ir junto; prazo e urgência, não.
- O coordenador autoriza ou recusa (com motivo). Também autoriza direto,
  sem pedido — mudança que vem do escritório: o pedido dele já nasce
  autorizado.
- O pedido é sobre o projeto LIBERADO para obra — é o que está sendo
  executado. Vários pedidos podem estar abertos ao mesmo tempo.
- Documento já liberado só aceita revisão nova com um pedido autorizado.
- Quem libera a revisão nova para obra marca quais pedidos autorizados ela
  atende: os marcados fecham ali; os outros seguem valendo.
- Até lá, o status do documento continua "liberado", com a marca de
  "revisão solicitada" ou "revisão autorizada" ao lado (18/09 e 05/10/2026).
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..enums import StatusArquivo, StatusRevisao, StatusSolicitacao
from ..models import Documento, Revisao, SolicitacaoRevisao
from ..schemas import AnexoOut, SolicitacaoOut, UsuarioOut

DESCRICAO_MIN = 10
DESCRICAO_MAX = 4000
MOTIVO_MIN = 10

# Com o pedido nesses estados, ainda dá para anexar: o do coordenador já nasce
# autorizado e recebe os anexos logo depois de criado.
ACEITA_ANEXO = {StatusSolicitacao.aberta, StatusSolicitacao.autorizada}

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


def problema_no_motivo(motivo: str | None) -> str | None:
    if not motivo or len(motivo) < MOTIVO_MIN:
        return (
            f"Diga por que a revisão não será feita (ao menos {MOTIVO_MIN} caracteres) "
            "— é o que quem pediu vai ler."
        )
    if len(motivo) > DESCRICAO_MAX:
        return f"O motivo pode ter no máximo {DESCRICAO_MAX} caracteres."
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
        decidida_em=solicitacao.decidida_em,
        decidida_por=(
            UsuarioOut.model_validate(solicitacao.decidida_por) if solicitacao.decidida_por else None
        ),
        motivo_recusa=solicitacao.motivo_recusa,
        anexos=[
            AnexoOut.model_validate(a)
            for a in solicitacao.anexos
            if a.status == StatusArquivo.disponivel
        ],
    )


def contagens_por_documento(
    db: Session, documento_ids: list[int]
) -> dict[int, dict[StatusSolicitacao, int]]:
    """Pedidos abertos e autorizados de cada documento — as marcas da lista."""
    if not documento_ids:
        return {}
    contagens: dict[int, dict[StatusSolicitacao, int]] = {}
    for documento_id, situacao, total in db.execute(
        select(
            SolicitacaoRevisao.documento_id,
            SolicitacaoRevisao.status,
            func.count(SolicitacaoRevisao.id),
        )
        .where(
            SolicitacaoRevisao.documento_id.in_(documento_ids),
            SolicitacaoRevisao.status.in_(
                [StatusSolicitacao.aberta, StatusSolicitacao.autorizada]
            ),
        )
        .group_by(SolicitacaoRevisao.documento_id, SolicitacaoRevisao.status)
    ):
        contagens.setdefault(documento_id, {})[situacao] = total
    return contagens


def bloqueio_de_revisao_nova(documento: Documento, numero: str) -> str | None:
    """Por que o documento não aceita a revisão `numero` agora, se não aceitar.

    Regra da TREELE (05/10/2026): revisão nova só depois que a anterior,
    liberada para obra, tiver revisão autorizada pelo coordenador. Documento
    novo — ou só com revisões canceladas — não tem anterior e passa.
    """
    validas = [r for r in documento.revisoes if r.status != StatusRevisao.cancelado]
    if not validas:
        return None
    anterior = max(validas, key=lambda r: (r.ordem, r.id))
    if anterior.status == StatusRevisao.em_revisao:
        return (
            f"A R{anterior.numero} de {documento.codigo} ainda está em revisão. "
            f"Mande os arquivos nela (R{anterior.numero}) ou peça ao coordenador para "
            f"cancelá-la antes de abrir a R{numero}."
        )
    if not any(s.status == StatusSolicitacao.autorizada for s in documento.solicitacoes):
        return (
            f"A R{anterior.numero} de {documento.codigo} está liberada para obra e não "
            "tem revisão autorizada. Revisão nova só depois que o coordenador autorizar, "
            "na tela do documento."
        )
    return None


def pedidos_marcados(db: Session, revisao: Revisao, ids: list[int]) -> list[SolicitacaoRevisao]:
    """Os pedidos marcados na liberação — só autorizados e do mesmo documento.
    Devolve None se algum não for: a tela estava desatualizada."""
    if not ids:
        return []
    pedidos = list(
        db.scalars(
            select(SolicitacaoRevisao).where(
                SolicitacaoRevisao.id.in_(set(ids)),
                SolicitacaoRevisao.documento_id == revisao.documento_id,
                SolicitacaoRevisao.status == StatusSolicitacao.autorizada,
            )
        )
    )
    return pedidos if len(pedidos) == len(set(ids)) else None


def atender(db: Session, revisao: Revisao, pedidos: list[SolicitacaoRevisao]) -> None:
    """Fecha os pedidos marcados: atendidos por esta revisão. Não faz commit."""
    agora = datetime.now(timezone.utc)
    for s in pedidos:
        s.status = StatusSolicitacao.atendida
        s.atendida_em = agora
        s.atendida_por_revisao_id = revisao.id
