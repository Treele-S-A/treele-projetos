"""Conflitos do 3D na correção de projeto (TREELE, 16/11/2026).

Um pedido de revisão (projeto liberado) ou uma reprovação (revisão em análise)
pode sair de vários conflitos de uma vez. Eles ficam ligados ao pedido ou à
reprovação e vão para a ata de análise crítica:

- a ata da revisão que traz a correção guarda, congelado, o quadro "Conflitos
  tratados nesta revisão": de onde veio (pedido ou reprovação) e a situação de
  cada conflito no dia da ata. Conflito que ainda aparece como ativo não impede
  a ata conforme: a tela avisa, e o quadro registra;
- a ata da revisão reprovada mostra, na "Solicitação de alterações", os
  conflitos apontados na reprovação.

Cada documento recebe só os conflitos em que ele aparece (lado A ou B).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import ContextoObra
from ..enums import StatusRevisao, StatusSolicitacao
from ..models import Conflito, Documento, Revisao, SolicitacaoRevisao

MAXIMO = 200

SITUACAO = {"novo": "Novo", "ativo": "Ativo", "aprovado": "Aprovado", "resolvido": "Resolvido"}
ABERTOS = {"novo", "ativo"}

# As categorias IFC como a tela mostra (frontend/src/modelo3d/resumo-ifc.ts).
CATEGORIAS_IFC = {
    "IFCBEAM": "Viga", "IFCCOLUMN": "Pilar", "IFCSLAB": "Laje / piso", "IFCWALL": "Parede",
    "IFCWALLSTANDARDCASE": "Parede", "IFCDOOR": "Porta", "IFCWINDOW": "Janela",
    "IFCMEMBER": "Perfil / montante", "IFCFOOTING": "Fundação", "IFCSTAIR": "Escada",
    "IFCFLOWSEGMENT": "Tubo / duto", "IFCFLOWFITTING": "Conexão", "IFCFLOWTERMINAL": "Terminal",
    "IFCFLOWCONTROLLER": "Registro / válvula", "IFCPIPESEGMENT": "Tubo", "IFCPIPEFITTING": "Conexão",
    "IFCDUCTSEGMENT": "Duto", "IFCCABLECARRIERSEGMENT": "Eletrocalha / eletroduto",
    "IFCBUILDINGELEMENTPROXY": "Outro elemento",
}


def categoria(codigo: str) -> str:
    return CATEGORIAS_IFC.get((codigo or "").upper(), (codigo or "").upper().replace("IFC", "").title())


class ConflitoInvalido(ValueError):
    pass


def _ve(ctx: ContextoObra, c: Conflito) -> bool:
    """A regra do painel de conflitos (api/conflitos.ve_conflito)."""
    if ctx.disciplinas is None:
        return True
    return any(d is not None and ctx.ve_disciplina(d.disciplina.codigo) for d in (c.documento_a, c.documento_b))


def escolher(db: Session, ctx: ContextoObra, documento: Documento, ids: list[int]) -> list[Conflito]:
    """Os conflitos marcados para o pedido ou a reprovação deste documento:
    da obra, à vista de quem pede, com o documento num dos lados e ainda não
    resolvidos."""
    ids = list(dict.fromkeys(ids or []))
    if not ids:
        return []
    if len(ids) > MAXIMO:
        raise ConflitoInvalido(f"Um pedido trata até {MAXIMO} conflitos.")
    achados = {c.id: c for c in db.scalars(select(Conflito).where(Conflito.id.in_(ids)))}
    escolhidos = []
    for i in ids:
        c = achados.get(i)
        if c is None or c.obra_id != ctx.obra.id or not _ve(ctx, c):
            raise ConflitoInvalido(f"Conflito #{i} não encontrado nesta obra.")
        if documento.id not in (c.documento_a_id, c.documento_b_id):
            raise ConflitoInvalido(f"O conflito #{i} não envolve {documento.codigo}.")
        if c.status == "resolvido":
            raise ConflitoInvalido(f"O conflito #{i} já está resolvido.")
        escolhidos.append(c)
    return escolhidos


def _lado(c: Conflito, qual: str) -> tuple[str, str | None]:
    doc = getattr(c, f"documento_{qual}")
    nome = getattr(c, f"nome_{qual}") or "sem nome"
    peca = f"{categoria(getattr(c, f'categoria_{qual}'))}: {nome}"
    return peca, (f"{doc.codigo} R{getattr(c, f'revisao_{qual}')}" if doc else None)


def linha(c: Conflito) -> dict:
    """O conflito como a ata o mostra (e guarda)."""
    peca_a, doc_a = _lado(c, "a")
    peca_b, doc_b = _lado(c, "b")
    disc = [d.disciplina.codigo if d else "?" for d in (c.documento_a, c.documento_b)]
    return {
        "id": c.id,
        "situacao": c.status,
        "tipo": c.tipo,
        "disciplinas": " × ".join(disc),
        "peca_a": peca_a,
        "documento_a": doc_a,
        "peca_b": peca_b,
        "documento_b": doc_b,
        "medida_cm": round((c.medida or 0) * 100, 1),
        "cota_m": round(c.centro[1], 2) if c.centro else None,
        "justificativa": c.justificativa,
        "visto_em": _data(c.visto_em),
        "resolvido_em": _data(c.resolvido_em),
    }


def resumo(c: Conflito) -> dict:
    """O conflito no cartão do pedido."""
    peca_a, doc_a = _lado(c, "a")
    peca_b, doc_b = _lado(c, "b")
    return {"id": c.id, "situacao": c.status, "texto": f"{peca_a} ({doc_a or '?'}) × {peca_b} ({doc_b or '?'})"}


def _revisao_no_conflito(c: Conflito, documento_id: int) -> str | None:
    if c.documento_a_id == documento_id:
        return c.revisao_a
    if c.documento_b_id == documento_id:
        return c.revisao_b
    return None


def _com_conferencia(c: Conflito, revisao: Revisao) -> dict:
    """A linha, dizendo se a última detecção já viu a revisão analisada: o
    conflito "ativo" visto só na revisão anterior ainda não foi conferido."""
    item = linha(c)
    vista = _revisao_no_conflito(c, revisao.documento_id)
    item["conferido"] = c.status not in ABERTOS or vista == revisao.numero
    item["revisao_vista"] = vista
    return item


def _data(valor: datetime | None) -> str | None:
    return valor.isoformat() if valor else None


def origens(db: Session, revisoes: list[Revisao]) -> list[dict]:
    """De onde vieram as correções destas revisões em análise, com os
    conflitos de cada uma: os pedidos autorizados do documento (que a revisão
    vai atender) e as reprovações desde a última liberada."""
    saida: list[dict] = []
    vistos: set[tuple[str, int]] = set()
    for revisao in revisoes:
        doc = revisao.documento
        pedidos = db.scalars(
            select(SolicitacaoRevisao)
            .where(
                SolicitacaoRevisao.documento_id == doc.id,
                (SolicitacaoRevisao.status == StatusSolicitacao.autorizada)
                | (SolicitacaoRevisao.atendida_por_revisao_id == revisao.id),
            )
            .order_by(SolicitacaoRevisao.id)
        ).all()
        for s in pedidos:
            if not s.conflitos or ("solicitacao", s.id) in vistos:
                continue
            vistos.add(("solicitacao", s.id))
            saida.append({
                "tipo": "solicitacao",
                "id": s.id,
                "documento": doc.codigo,
                "revisao": revisao.numero,
                "origem": f"Pedido de revisão sobre a R{s.revisao.numero}" if s.revisao else "Pedido de revisão",
                "data": _data(s.criada_em),
                "por": s.criada_por.nome if s.criada_por else None,
                "descricao": s.descricao,
                "conflitos": [_com_conferencia(c, revisao) for c in s.conflitos],
            })
        anteriores = [r for r in doc.revisoes if r.ordem < revisao.ordem and r.status != StatusRevisao.cancelado]
        corte = max(
            (r.ordem for r in anteriores if r.status in (StatusRevisao.liberado_para_obra, StatusRevisao.obsoleto)),
            default=-1,
        )
        for r in sorted(anteriores, key=lambda x: x.ordem):
            if r.status != StatusRevisao.reprovado or r.ordem <= corte or not r.conflitos_reprovacao:
                continue
            if ("reprovacao", r.id) in vistos:
                continue
            vistos.add(("reprovacao", r.id))
            saida.append({
                "tipo": "reprovacao",
                "id": r.id,
                "documento": doc.codigo,
                "revisao": revisao.numero,
                "origem": f"Reprovação da R{r.numero}",
                "data": _data(r.reprovada_em),
                "por": r.reprovada_por.nome if r.reprovada_por else None,
                "descricao": r.observacao,
                "conflitos": [_com_conferencia(c, revisao) for c in r.conflitos_reprovacao],
            })
    return saida
