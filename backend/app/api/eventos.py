"""Consulta da trilha de auditoria."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from ..deps import ContextoObra, contexto_obra
from ..models import Evento
from ..schemas import EventoOut, Pagina

router = APIRouter(tags=["auditoria"])


@router.get("/obras/{obra_id}/eventos", response_model=Pagina[EventoOut])
def listar(
    acao: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    ctx: ContextoObra = Depends(contexto_obra),
):
    ctx.exigir("gerenciar", "Somente o coordenador da obra vê a trilha de auditoria.")

    consulta = select(Evento).where(Evento.obra_id == ctx.obra.id)
    if acao:
        consulta = consulta.where(Evento.acao == acao)

    total = ctx.db.scalar(
        select(func.count()).select_from(consulta.order_by(None).subquery())
    )
    itens = list(
        ctx.db.scalars(
            consulta.order_by(Evento.criado_em.desc(), Evento.id.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        )
    )
    return Pagina[EventoOut](
        itens=[EventoOut.model_validate(e) for e in itens],
        total=total or 0,
        pagina=pagina,
        por_pagina=por_pagina,
    )
