"""Catálogo de documentos — a "lista mestra" da obra.

A revisão atual de um documento é a de maior ordem que não foi cancelada. O
status dela é o status do documento: se a maior revisão está "em revisão", o
documento tem pendência; se está "liberado para obra", é o que vale em campo.
"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..db import get_db
from ..deps import ContextoObra, contexto_obra, montar_contexto, usuario_atual
from ..enums import StatusRevisao, TipoArquivo
from ..models import Arquivo, Disciplina, Documento, Fase, Revisao, Usuario
from ..schemas import (
    DocumentoAtualizar,
    DocumentoDetalhe,
    DocumentoOut,
    Pagina,
    RevisaoOut,
    RevisaoResumo,
)
from ..services import auditoria

router = APIRouter(tags=["documentos"])


def _subconsulta_atual():
    """(documento_id, ordem da revisão atual)."""
    return (
        select(
            Revisao.documento_id.label("doc_id"),
            func.max(Revisao.ordem).label("max_ordem"),
        )
        .where(Revisao.status != StatusRevisao.cancelado)
        .group_by(Revisao.documento_id)
        .subquery()
    )


def _consulta_base(obra_id: int):
    sub = _subconsulta_atual()
    atual = aliased(Revisao)
    consulta = (
        select(Documento, atual)
        .join(sub, sub.c.doc_id == Documento.id)
        .join(
            atual,
            and_(atual.documento_id == Documento.id, atual.ordem == sub.c.max_ordem),
        )
        .where(Documento.obra_id == obra_id)
    )
    return consulta, atual


def _aplicar_filtros(
    consulta,
    atual,
    *,
    disciplina_id: int | None,
    fase_id: int | None,
    status_revisao: StatusRevisao | None,
    tipo: TipoArquivo | None,
    busca: str | None,
):
    if disciplina_id:
        consulta = consulta.where(Documento.disciplina_id == disciplina_id)
    if fase_id:
        consulta = consulta.where(Documento.fase_id == fase_id)
    if status_revisao:
        consulta = consulta.where(atual.status == status_revisao)
    if tipo:
        consulta = consulta.where(
            select(Arquivo.id)
            .join(Revisao, Revisao.id == Arquivo.revisao_id)
            .where(Revisao.documento_id == Documento.id, Arquivo.tipo == tipo)
            .exists()
        )
    if busca:
        alvo = f"%{busca.strip()}%"
        consulta = consulta.where(
            or_(Documento.codigo.ilike(alvo), Documento.titulo.ilike(alvo))
        )
    return consulta


def _montar_saida(db: Session, linhas) -> list[DocumentoOut]:
    if not linhas:
        return []
    ids = [d.id for d, _ in linhas]
    contagens = dict(
        db.execute(
            select(Revisao.documento_id, func.count(Revisao.id))
            .where(Revisao.documento_id.in_(ids))
            .group_by(Revisao.documento_id)
        ).all()
    )
    saida = []
    for documento, atual in linhas:
        item = DocumentoOut.model_validate(documento)
        item.total_revisoes = contagens.get(documento.id, 0)
        item.revisao_atual = RevisaoResumo.model_validate(atual)
        saida.append(item)
    return saida


@router.get("/obras/{obra_id}/documentos", response_model=Pagina[DocumentoOut])
def listar(
    disciplina_id: int | None = None,
    fase_id: int | None = None,
    status_revisao: StatusRevisao | None = None,
    tipo: TipoArquivo | None = None,
    busca: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    ctx: ContextoObra = Depends(contexto_obra),
):
    consulta, atual = _consulta_base(ctx.obra.id)
    consulta = _aplicar_filtros(
        consulta, atual,
        disciplina_id=disciplina_id, fase_id=fase_id,
        status_revisao=status_revisao, tipo=tipo, busca=busca,
    )

    # Cliente não enxerga o que ainda não foi liberado.
    if not ctx.pode("ver_obsoletos"):
        consulta = consulta.where(atual.status == StatusRevisao.liberado_para_obra)

    total = ctx.db.scalar(
        select(func.count()).select_from(consulta.order_by(None).subquery())
    )

    linhas = ctx.db.execute(
        consulta.order_by(Documento.codigo)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()

    return Pagina[DocumentoOut](
        itens=_montar_saida(ctx.db, linhas),
        total=total or 0,
        pagina=pagina,
        por_pagina=por_pagina,
    )


@router.get("/obras/{obra_id}/documentos/exportar")
def exportar(
    disciplina_id: int | None = None,
    fase_id: int | None = None,
    status_revisao: StatusRevisao | None = None,
    request: Request = None,
    ctx: ContextoObra = Depends(contexto_obra),
):
    """Lista mestra em CSV — o relatório que sempre pedem em reunião."""
    consulta, atual = _consulta_base(ctx.obra.id)
    consulta = _aplicar_filtros(
        consulta, atual,
        disciplina_id=disciplina_id, fase_id=fase_id,
        status_revisao=status_revisao, tipo=None, busca=None,
    )
    if not ctx.pode("ver_obsoletos"):
        consulta = consulta.where(atual.status == StatusRevisao.liberado_para_obra)

    linhas = ctx.db.execute(consulta.order_by(Documento.codigo)).all()

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(
        [
            "Código", "Título", "Disciplina", "Fase",
            "Revisão atual", "Status", "Publicada em",
            "Total de revisões", "Arquivos",
        ]
    )
    for documento, revisao in linhas:
        arquivos = ", ".join(sorted({a.tipo.value.upper() for a in revisao.arquivos}))
        escritor.writerow(
            [
                documento.codigo,
                documento.titulo or "",
                documento.disciplina.codigo,
                documento.fase.codigo,
                f"R{revisao.numero}",
                revisao.status.rotulo,
                revisao.publicada_em.strftime("%d/%m/%Y %H:%M")
                if revisao.publicada_em
                else "",
                len(documento.revisoes),
                arquivos,
            ]
        )

    auditoria.registrar(
        ctx.db, acao="lista_mestra_exportada", entidade="obra",
        entidade_id=ctx.obra.id, usuario=ctx.usuario, obra_id=ctx.obra.id,
        detalhes={"linhas": len(linhas)}, request=request,
    )
    ctx.db.commit()

    nome = f"lista-mestra-{ctx.obra.codigo}-{datetime.now():%Y%m%d}.csv"
    # BOM para o Excel brasileiro abrir com acentuação correta.
    conteudo = "﻿" + buffer.getvalue()
    return StreamingResponse(
        iter([conteudo]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/documentos/{documento_id}", response_model=DocumentoDetalhe)
def detalhe(
    documento_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    ctx = montar_contexto(db, usuario, documento.obra_id)

    revisoes = sorted(documento.revisoes, key=lambda r: r.ordem, reverse=True)
    if not ctx.pode("ver_obsoletos"):
        revisoes = [r for r in revisoes if r.status == StatusRevisao.liberado_para_obra]

    saida = DocumentoDetalhe.model_validate(documento)
    saida.total_revisoes = len(documento.revisoes)
    saida.revisoes = [RevisaoOut.model_validate(r) for r in revisoes]

    atual = next(
        (r for r in revisoes if r.status != StatusRevisao.cancelado), None
    )
    saida.revisao_atual = RevisaoResumo.model_validate(atual) if atual else None
    return saida


@router.patch("/documentos/{documento_id}", response_model=DocumentoOut)
def atualizar(
    documento_id: int,
    dados: DocumentoAtualizar,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    ctx = montar_contexto(db, usuario, documento.obra_id)
    ctx.exigir("enviar")

    if dados.titulo is not None:
        documento.titulo = dados.titulo.strip() or None

    auditoria.registrar(
        db, acao="documento_atualizado", entidade="documento",
        entidade_id=documento.id, usuario=usuario, obra_id=documento.obra_id,
        request=request,
    )
    db.commit()

    saida = DocumentoOut.model_validate(documento)
    saida.total_revisoes = len(documento.revisoes)
    return saida
